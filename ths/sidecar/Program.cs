// ThsSidecar — ths 插件的实时五档 sidecar（常驻进程）
//
// 路线：宿主加载同花顺 Linux 客户端（cn.com.10jqka 2.9.1.0）自己的托管行情
// 程序集（Hevo.Api.Quotes 的 QuoteV2/V3 DataCenter），借客户端代码完成
// verify2 鉴权与二进制行情协议，本进程只做会话保活与本地 IPC 转发。
// 验证记录见 ~/workspace/ths/gms_poc_result.md（2b：账号 Passport 下 id=200
// 首请求即应答，五档与 Web 网关逐值核对一致；游客 Passport 被服务端策略
// 静默丢弃，故本 sidecar 只用账号通道）。
//
// IPC：Unix domain socket（默认 ~/.ths_sidecar.sock），行分隔 JSON：
//   {"cmd":"status"}
//   {"cmd":"realtime","codes":["USHA600519","USZA000977","USTM920185"]}
//   {"cmd":"shutdown"}
// 凭据只从 ~/.ths_auth.json 读取（ths login 的 checkSms 工件），日志一律掩码，
// 绝不打印 password / Passport / Session 原文。
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Net.Http;
using System.Net.Sockets;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Hevo.Core;
using Hevo.Core.Auth.V1;
using Hevo.Core.Operations;
using Hevo.Core.Protocols;
using Normandy.Identity.Client.Application.Contracts.Dto;

class Sidecar
{
    const string FilesDir = "/opt/apps/cn.com.10jqka/files";
    const string ExpectedClientVersion = "2.9.1.0";
    static string HomeDir = Environment.GetFolderPath(Environment.SpecialFolder.UserProfile);
    static string SockPath = Path.Combine(HomeDir, ".ths_sidecar.sock");
    static string LogPath = Path.Combine(HomeDir, ".ths_sidecar.log");
    static string PidPath = Path.Combine(HomeDir, ".ths_sidecar.pid");
    static string AuthPath = Path.Combine(HomeDir, ".ths_auth.json");

    static TextWriter _stderr0;
    static StreamWriter _log;
    static readonly object _logLock = new object();

    static string _state = "starting"; // starting | online | offline | error
    static string _lastError = null;
    static string _account = null;
    static DateTime? _sessionExpires = null;
    static bool _isLevel2 = false;
    static AuthTokenV1 _token = null;
    static string _passwd = null;
    static readonly DateTime _startedAt = DateTime.Now;
    static readonly SemaphoreSlim _reqLock = new SemaphoreSlim(1, 1);
    static Dictionary<int, string> _fieldNames = null;
    static Dictionary<string, int> _fidByName = null;

    static void Log(string msg)
    {
        var line = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss") + " " + msg;
        lock (_logLock)
        {
            try { _log?.WriteLine(line); _log?.Flush(); } catch { }
        }
    }

    static void Fatal(string code, string msg)
    {
        Log("FATAL " + code + ": " + msg);
        _stderr0?.WriteLine(JsonSerializer.Serialize(new { error = msg, code }));
        Environment.Exit(10);
    }

    static string Mask(string v)
    {
        if (string.IsNullOrEmpty(v)) return "<empty>";
        return v.Length <= 4 ? "****" : v.Substring(0, 2) + "****(len=" + v.Length + ")";
    }

    // ------------------------------------------------------------ startup

    static void CheckClient()
    {
        if (!Directory.Exists(FilesDir))
            Fatal("CLIENT_MISSING",
                "同花顺 Linux 客户端未安装（缺 " + FilesDir + "）。" +
                "重装：sudo dpkg -i ths_linux_amd64.deb（cn.com.10jqka 2.9.1.0），" +
                "安装包见 https://www.10jqka.com.cn 官方下载页。");
        var b2c = Path.Combine(FilesDir, "HevoNext.B2CApp.dll");
        string ver = null;
        try { ver = FileVersionInfo.GetVersionInfo(b2c).FileVersion; } catch { }
        if (ver != ExpectedClientVersion)
            Fatal("CLIENT_VERSION",
                "客户端版本不匹配：期望 " + ExpectedClientVersion + "，实测 " +
                (ver ?? "<unknown>") + "（" + b2c + "）。本 sidecar 强绑定 2.9.1.0 " +
                "程序集与 C-Version 盖章，客户端升级后需重新验证再放行。");
    }

    static void LoadAuth()
    {
        if (!File.Exists(AuthPath))
            Fatal("AUTH_MISSING", "未登录：先执行 ths login send-code / verify 完成短信登录（凭据存 ~/.ths_auth.json）。");
        string account = null, passwd = null; long expire = 0;
        try
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(AuthPath));
            var r = doc.RootElement;
            account = r.TryGetProperty("account", out var a) ? a.GetString() : null;
            passwd = r.TryGetProperty("password", out var p) ? p.GetString() : null;
            if (r.TryGetProperty("expireTime", out var e) && e.ValueKind == JsonValueKind.Number)
                expire = e.GetInt64();
        }
        catch (Exception ex) { Fatal("AUTH_INVALID", "~/.ths_auth.json 解析失败: " + ex.Message); }
        if (string.IsNullOrEmpty(account) || string.IsNullOrEmpty(passwd))
            Fatal("AUTH_INVALID", "~/.ths_auth.json 缺 account/password，先重新 ths login。");
        if (expire > 0 && DateTimeOffset.FromUnixTimeSeconds(expire).LocalDateTime < DateTime.Now)
            Fatal("AUTH_EXPIRED", "登录凭据（passwd 工件）已过期，先重新 ths login 刷新。");
        _account = account; _passwd = passwd;
        Log("auth loaded: account=" + account + " passwd=" + Mask(passwd) +
            (expire > 0 ? " passwd_expires=" + DateTimeOffset.FromUnixTimeSeconds(expire).LocalDateTime.ToString("yyyy-MM-dd HH:mm") : ""));
    }

    static async Task<bool> VerifyAsync()
    {
        var loginToken = new AuthLoginTokenV1
        {
            Account = _account,
            AccountToken = _passwd,
            LoginMode = AuthRequestType.MD5
        };
        AuthTokenV1 token = null;
        try { token = await AuthCenter.AuthAsync(loginToken); }
        catch (Exception ex) { _lastError = "verify2 exception: " + ex.Message; Log(_lastError); return false; }
        if (token == null || token.Info == null || token.Info.IsBad || token.AuthPassport == null || token.AuthPassport.IsBad)
        {
            _lastError = "verify2 failed: " + (token?.Info?.ErrorMessage ?? string.Join(" | ", AuthCenter.ErrorMessage ?? new List<string>()));
            Log(_lastError);
            return false;
        }
        _token = token;
        _isLevel2 = token.AuthPassport.IsLevel2;
        var expObj = (object)token.Info.Expires;
        _sessionExpires = expObj is DateTime dt ? dt
            : (DateTime.TryParse(Convert.ToString(expObj), out var parsed) ? parsed : (DateTime?)null);
        DataCenter.Current.UserToken = token;
        Log("verify2 ok: userid=" + token.Info.UserID +
            " session_expires=" + (_sessionExpires?.ToString("yyyy-MM-dd HH:mm:ss") ?? "?") +
            " is_level2=" + _isLevel2 +
            " groups V2x" + (token.AuthPassport.ServerGroupsV2?.Count ?? 0) +
            "/V3x" + (token.AuthPassport.ServerGroupsV3?.Count ?? 0));
        return true;
    }

    // 本沙箱/部分网络下 DNS 对行情主机名返回合成地址、二进制协议无响应；
    // 真实客户端由 HTTPDNS(HTTPDNS 组件) 把真实 IP 写进 DnsCache 再合并地址表。
    // 这里复刻 PoC 已实证的预填：静态表（客户端自带 workspace/DNSCache.json 与
    // 公开 DoH 互相印证）+ 对其余主机名组走 DoH 动态解析。
    static async Task SeedDnsAsync()
    {
        var seed = new Dictionary<string, string[]>
        {
            ["hevozhuhq1.123ths.com"] = new[] { "8.132.233.71", "8.134.118.59" },
            ["hevofu1.123ths.com"] = new[] { "8.134.111.93", "119.3.25.251" },
            ["hevoinfo1.123ths.com"] = new[] { "119.3.25.251", "8.134.114.144" },
            ["hevofunction1.123ths.com"] = new[] { "8.134.119.116", "119.3.16.177" },
            ["hevofuhq2.123ths.com"] = new[] { "8.132.233.57", "8.132.233.56" },
        };
        foreach (var kv in seed) DnsCache.CacheDns[kv.Key] = new List<string>(kv.Value);
        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(15) };
            var hosts = new HashSet<string>();
            if (_token?.AuthPassport?.ServerGroupsV2 != null)
                foreach (var g in _token.AuthPassport.ServerGroupsV2) if (!string.IsNullOrEmpty(g.HostOrIp)) hosts.Add(g.HostOrIp);
            if (_token?.AuthPassport?.ServerGroupsV3 != null)
                foreach (var g in _token.AuthPassport.ServerGroupsV3) if (!string.IsNullOrEmpty(g.HostOrIp)) hosts.Add(g.HostOrIp);
            foreach (var host in hosts)
            {
                if (System.Net.IPAddress.TryParse(host, out _) || DnsCache.CacheDns.ContainsKey(host)) continue;
                try
                {
                    var json = await http.GetStringAsync("https://223.5.5.5/resolve?name=" + host + "&type=A");
                    var ips = Newtonsoft.Json.Linq.JObject.Parse(json)["Answer"]?
                        .Select(a => (string)a["data"])
                        .Where(s => System.Net.IPAddress.TryParse(s, out _)).Take(3).ToList()
                        ?? new List<string>();
                    if (ips.Count > 0) { DnsCache.CacheDns[host] = ips; Log("dns seed " + host + " -> " + string.Join(",", ips)); }
                }
                catch (Exception ex) { Log("dns seed " + host + " failed: " + ex.Message); }
            }
        }
        catch (Exception ex) { Log("dns seed dyn failed: " + ex.Message); }
    }

    static async Task<bool> TryStartAsync()
    {
        try
        {
            var ok = await DataCenter.Current.TryStartAsync();
            Log("TryStartAsync=" + ok + " IsOnline=" + DataCenter.Current.IsOnline);
            return ok && DataCenter.Current.IsOnline;
        }
        catch (Exception ex) { _lastError = "TryStart exception: " + ex.Message; Log(_lastError); return false; }
    }

    static async Task ConnectFlowAsync(bool first)
    {
        if (!await VerifyAsync()) { _state = "error"; return; }
        await SeedDnsAsync();
        for (int i = 1; i <= 6; i++)
        {
            if (await TryStartAsync())
            {
                _state = "online"; _lastError = null;
                await Task.Delay(2000); // settle: 等各会话完成登录
                return;
            }
            _state = "offline"; _lastError = "TryStartAsync failed (sessions not online)";
            if (first) await Task.Delay(15000);
            else break;
        }
    }

    static async Task SupervisorAsync()
    {
        while (true)
        {
            await Task.Delay(TimeSpan.FromMinutes(1));
            try
            {
                bool sessionStale = _sessionExpires == null ||
                                    DateTime.Now > _sessionExpires.Value.AddMinutes(-30);
                if (_token == null || sessionStale)
                {
                    Log("supervisor: session stale, re-verify");
                    if (await VerifyAsync()) { await SeedDnsAsync(); if (!DataCenter.Current.IsOnline) await TryStartAsync(); }
                    _state = DataCenter.Current.IsOnline ? "online" : "offline";
                }
                else if (!DataCenter.Current.IsOnline)
                {
                    Log("supervisor: offline, retry TryStart");
                    _state = await TryStartAsync() ? "online" : "offline";
                }
                else _state = "online";
            }
            catch (Exception ex) { Log("supervisor error: " + ex.Message); }
        }
    }

    // ------------------------------------------------------------ realtime

    static readonly QuoteField[] RtFields =
    {
        QuoteFields.date_time, QuoteFields.prev_close, QuoteFields.open, QuoteFields.high,
        QuoteFields.low, QuoteFields.latest, QuoteFields.close, QuoteFields.transaction_volume,
        QuoteFields.transaction_amount,
        QuoteFields.bid_price_1, QuoteFields.bid_count_1, QuoteFields.bid_price_2, QuoteFields.bid_count_2,
        QuoteFields.bid_price_3, QuoteFields.bid_count_3, QuoteFields.bid_price_4, QuoteFields.bid_count_4,
        QuoteFields.bid_price_5, QuoteFields.bid_count_5,
        QuoteFields.ask_price_1, QuoteFields.ask_count_1, QuoteFields.ask_price_2, QuoteFields.ask_count_2,
        QuoteFields.ask_price_3, QuoteFields.ask_count_3, QuoteFields.ask_price_4, QuoteFields.ask_count_4,
        QuoteFields.ask_price_5, QuoteFields.ask_count_5,
    };

    // 注意：fid 并不与字段名一一对应（如 fid 13 同时是 transaction_volume 与
    // transaction_volume_shou），故结构化提取一律走 name->fid，fid->name 只作参考。
    static void BuildFieldNames()
    {
        _fieldNames = new Dictionary<int, string>();
        _fidByName = new Dictionary<string, int>();
        var t = typeof(QuoteFields);
        foreach (var p in t.GetProperties(BindingFlags.Public | BindingFlags.Static))
            if (p.PropertyType == typeof(QuoteField) && p.GetValue(null) is QuoteField qf)
            {
                int fid = Convert.ToInt32(qf.FieldID);
                if (!_fieldNames.ContainsKey(fid)) _fieldNames[fid] = p.Name;
                if (!_fidByName.ContainsKey(p.Name)) _fidByName[p.Name] = fid;
            }
        foreach (var f in t.GetFields(BindingFlags.Public | BindingFlags.Static))
            if (f.FieldType == typeof(QuoteField) && f.GetValue(null) is QuoteField qf)
            {
                int fid = Convert.ToInt32(qf.FieldID);
                if (!_fieldNames.ContainsKey(fid)) _fieldNames[fid] = f.Name;
                if (!_fidByName.ContainsKey(f.Name)) _fidByName[f.Name] = fid;
            }
    }

    static object JsonVal(object v)
    {
        switch (v)
        {
            case null: return null;
            case double db: return double.IsNaN(db) || double.IsInfinity(db) ? null : (object)db;
            case float fl: return float.IsNaN(fl) || float.IsInfinity(fl) ? null : (object)(double)fl;
            case decimal dc: return (double)dc;
            case DateTime dtv: return dtv.ToString("yyyy-MM-dd HH:mm:ss");
            case bool b: return b;
            case string s: return s;
            case IConvertible: return Convert.ToDouble(v);
            default: return v.ToString();
        }
    }

    static double? Num(Dictionary<int, object> m, string name)
    {
        if (!_fidByName.TryGetValue(name, out var fid)) return null;
        if (!m.TryGetValue(fid, out var v) || v == null) return null;
        try { var d = Convert.ToDouble(v); return double.IsNaN(d) ? (double?)null : d; }
        catch { return null; }
    }

    static object DateTimeVal(Dictionary<int, object> m)
    {
        // date_time 为 fid 1：实测服务端对快照请求不回该字段，缺失时如实 null。
        if (!_fidByName.TryGetValue("date_time", out var fid)) return null;
        if (!m.TryGetValue(fid, out var v)) return null;
        return JsonVal(v);
    }

    static List<object> Book(Dictionary<int, object> m, string kind)
    {
        var list = new List<object>();
        for (int i = 1; i <= 5; i++)
        {
            var price = Num(m, kind + "_price_" + i);
            var count = Num(m, kind + "_count_" + i);
            list.Add(new Dictionary<string, object> { ["price"] = price, ["count"] = count });
        }
        return list;
    }

    static async Task<Dictionary<string, object>> RealtimeOneAsync(string secText)
    {
        var row = new Dictionary<string, object> { ["security"] = secText };
        Security sec;
        try { sec = new Security(secText); }
        catch (Exception ex) { row["error"] = "bad security: " + ex.Message; return row; }
        row["code"] = sec.Code.ToString();
        row["market"] = sec.Market.ToString();
        if (_state != "online")
        {
            row["error"] = "sidecar not online (state=" + _state + (string.IsNullOrEmpty(_lastError) ? "" : ", " + _lastError) + ")";
            return row;
        }
        for (int attempt = 1; attempt <= 3; attempt++)
        {
            List<DataResponseV2> respList = null;
            try
            {
                var call = DataCenter.Current.RequestRealtimeV2(sec, RtFields);
                var done = await Task.WhenAny(call, Task.Delay(TimeSpan.FromSeconds(45)));
                if (done == call) respList = (await call)?.ToList();
            }
            catch (Exception ex) { Log("realtime " + secText + " attempt " + attempt + " EX: " + ex.Message); }
            if (respList != null && respList.Any(r => !r.IsBad))
            {
                var reply = new RealtimeReplyData(respList);
                Dictionary<Field, object> fields = null;
                foreach (var kv in reply.data)
                    if (kv.Key.ToString() == sec.ToString()) { fields = kv.Value; break; }
                if (fields == null && reply.data.Count == 1)
                    fields = reply.data.Values.First();
                if (fields == null) { row["error"] = "security missing in reply"; return row; }
                var byFid = new Dictionary<int, object>();
                var raw = new Dictionary<string, object>();
                foreach (var kv in fields)
                {
                    int fid = Convert.ToInt32(kv.Key.FieldID);
                    byFid[fid] = kv.Value;
                    raw[fid.ToString()] = JsonVal(kv.Value);
                }
                row["date_time"] = DateTimeVal(byFid);
                row["prev_close"] = Num(byFid, "prev_close");
                row["open"] = Num(byFid, "open");
                row["high"] = Num(byFid, "high");
                row["low"] = Num(byFid, "low");
                row["latest"] = Num(byFid, "latest");
                row["close"] = Num(byFid, "close");
                row["volume"] = Num(byFid, "transaction_volume");
                row["amount"] = Num(byFid, "transaction_amount");
                row["bid"] = Book(byFid, "bid");
                row["ask"] = Book(byFid, "ask");
                row["fields"] = raw;
                return row;
            }
            if (attempt < 3) await Task.Delay(2000);
        }
        row["error"] = "no response from quote server (bad/timeout after 3 attempts)";
        return row;
    }

    // ------------------------------------------------------------ IPC

    static Dictionary<string, object> StatusObj()
    {
        return new Dictionary<string, object>
        {
            ["ok"] = true,
            ["state"] = _state,
            ["online"] = _state == "online",
            ["account"] = _account,
            ["session_expires"] = _sessionExpires?.ToString("yyyy-MM-ddTHH:mm:ss"),
            ["is_level2"] = _isLevel2,
            ["client_version"] = ExpectedClientVersion,
            ["started_at"] = _startedAt.ToString("yyyy-MM-ddTHH:mm:ss"),
            ["pid"] = Environment.ProcessId,
            ["last_error"] = _lastError,
        };
    }

    static async Task<string> HandleAsync(string line)
    {
        JsonDocument doc;
        try { doc = JsonDocument.Parse(line); }
        catch { return "{\"ok\":false,\"error\":\"bad json\"}"; }
        using (doc)
        {
            var root = doc.RootElement;
            var cmd = root.TryGetProperty("cmd", out var c) ? c.GetString() : null;
            if (cmd == "status")
                return JsonSerializer.Serialize(StatusObj());
            if (cmd == "shutdown")
            {
                _ = Task.Run(async () => { await Task.Delay(300); Environment.Exit(0); });
                return "{\"ok\":true,\"bye\":true}";
            }
            if (cmd == "realtime")
            {
                var codes = new List<string>();
                if (root.TryGetProperty("codes", out var arr) && arr.ValueKind == JsonValueKind.Array)
                    foreach (var e in arr.EnumerateArray()) if (e.ValueKind == JsonValueKind.String) codes.Add(e.GetString());
                var results = new List<object>();
                await _reqLock.WaitAsync();
                try
                {
                    foreach (var code in codes) results.Add(await RealtimeOneAsync(code));
                }
                finally { _reqLock.Release(); }
                return JsonSerializer.Serialize(new Dictionary<string, object>
                {
                    ["ok"] = true, ["results"] = results
                });
            }
            return "{\"ok\":false,\"error\":\"unknown cmd\"}";
        }
    }

    static async Task ServeConnAsync(Socket conn)
    {
        using (conn)
        {
            try
            {
                conn.ReceiveTimeout = 15000;
                var buf = new List<byte>();
                var chunk = new byte[4096];
                string line = null;
                while (true)
                {
                    int n = conn.Receive(chunk);
                    if (n <= 0) return;
                    for (int i = 0; i < n; i++)
                    {
                        if (chunk[i] == (byte)'\n') { line = Encoding.UTF8.GetString(buf.ToArray()); break; }
                        buf.Add(chunk[i]);
                    }
                    if (line != null) break;
                    if (buf.Count > 65536) return;
                }
                if (string.IsNullOrWhiteSpace(line)) return;
                var resp = await HandleAsync(line);
                var bytes = Encoding.UTF8.GetBytes(resp + "\n");
                conn.Send(bytes);
            }
            catch (Exception ex) { Log("conn error: " + ex.Message); }
        }
    }

    // ------------------------------------------------------------ main

    static async Task<int> Main(string[] args)
    {
        _stderr0 = Console.Error;
        for (int i = 0; i + 1 < args.Length; i++)
        {
            if (args[i] == "--socket") SockPath = args[i + 1];
            else if (args[i] == "--log") LogPath = args[i + 1];
            else if (args[i] == "--pidfile") PidPath = args[i + 1];
        }
        _log = new StreamWriter(new FileStream(LogPath, FileMode.Append, FileAccess.Write, FileShare.ReadWrite)) { AutoFlush = true };
        Console.SetOut(_log);
        Console.SetError(_log);
        Log("=== ThsSidecar starting (pid " + Environment.ProcessId + ") ===");

        CheckClient();
        LoadAuth();

        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);
        AppDomain.CurrentDomain.AssemblyResolve += (s, e) =>
        {
            var p = Path.Combine(FilesDir, new AssemblyName(e.Name).Name + ".dll");
            return File.Exists(p) ? Assembly.LoadFrom(p) : null;
        };
        BuildFieldNames();
        Log("field map: " + _fidByName.Count + " quote field names");

        try
        {
            NetworkManager.Current.CreateProxyProvider();
            AuthCenter.Initial("同花顺远航版", new AuthAppInfo
            {
                Appid = "2022021120720687",
                EncryptedKey = "fCB+KE6AkKX4aIX8TenHxwPNztfT1j6jL/nj3Mwbnm0=",
                InitialValue = "hevoclientpc0000"
            }, null);
            Log("AuthCenter.Initial ok");
        }
        catch (Exception ex) { Fatal("INIT", "AuthCenter.Initial 失败: " + ex.Message); }

        // bind socket early so `ths rt status` works during startup
        if (File.Exists(SockPath)) File.Delete(SockPath);
        var listener = new Socket(AddressFamily.Unix, SocketType.Stream, ProtocolType.Unspecified);
        listener.Bind(new UnixDomainSocketEndPoint(SockPath));
        try { File.SetUnixFileMode(SockPath, UnixFileMode.UserRead | UnixFileMode.UserWrite); } catch { }
        listener.Listen(16);
        File.WriteAllText(PidPath, Environment.ProcessId.ToString());
        AppDomain.CurrentDomain.ProcessExit += (s, e) =>
        {
            try { File.Delete(PidPath); } catch { }
            try { File.Delete(SockPath); } catch { }
        };
        Log("listening on " + SockPath);

        _ = Task.Run(async () =>
        {
            await ConnectFlowAsync(true);
            Log("state=" + _state);
            _ = SupervisorAsync();
        });

        while (true)
        {
            Socket conn;
            try { conn = await listener.AcceptAsync(); }
            catch (Exception ex) { Log("accept error: " + ex.Message); continue; }
            _ = ServeConnAsync(conn);
        }
    }
}
