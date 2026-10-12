# ths sidecar（实时五档通道）

`ths rt` 的后端：一个常驻 .NET 8 进程，宿主加载**同花顺 Linux 客户端
2.9.1.0 自己的** `Hevo.Api.Quotes` 等程序集，借客户端代码完成 verify2
鉴权（AuthCenter）与 QuoteV2/V3 二进制行情协议（DataCenter），把实时
快照（含完整买卖五档）经本地 Unix socket 提供给 `ths.py`。

为什么需要它：Web 网关（`ths quote`）盘口只下发买一/卖一；完整五档是
客户端实时通道的 L1 标准字段。路线已经三轮实证（2026-10-12）：游客
Passport 会被服务端策略静默丢弃 id=200 请求，**账号 Passport 首请求即
应答**，五档与网关参考值逐值核对一致。十档/逐笔是 Level-2 付费权益
（Passport 的 IsLevel2 位，服务端签名），未订购的账号拿不到，本组件
不越权。

## 前置条件

1. 同花顺 Linux 客户端 **2.9.1.0** 已安装：`/opt/apps/cn.com.10jqka/files/`
   存在且 `HevoNext.B2CApp.dll` 版本为 2.9.1.0（强绑定：csproj 引用其
   程序集，且宿主程序集的 ProductName/FileVersion 盖章为
   `hevo_linux_uos / 2.9.1.0` 以对齐客户端 C-Version；版本不符启动即
   报错退出）。重装：`sudo dpkg -i ths_linux_amd64.deb`。
2. .NET 8 SDK/运行时（构建与运行）。运行时查找顺序：PATH、
   `DOTNET_ROOT`、`~/workspace/.dotnet`、`~/.dotnet`。
3. 已 `ths login`：凭据 `~/.ths_auth.json` 中的 checkSms 工件
   （account/passwd）就是 verify2 的入参；passwd 过期（约 30 天）需重登。
4. 网络：行情服务器走直连 TCP（8601/8602/9601/9602 等）。在 Muse
   沙箱里需 Settings → Permissions → Direct network protocols 把
   **other_tcp 改为 Ask** 并逐目的地批准连接。

## 构建

```bash
./build.sh   # dotnet publish -c Release -o bin/
```

产物在 `bin/`（`ThsSidecar.dll` + apphost + `workspace/datacenter.xml`）。
`datacenter.xml` 为客户端出厂文件副本（DataCenter 按入口程序集路径读
`workspace/datacenter.xml`）。

## 运行与 IPC

`ths rt <代码>` 发现 sidecar 未运行时自动 detached 拉起（日志
`~/.ths_sidecar.log`），无需手工启动。手工管理：

```bash
ths rt status   # 在线状态、会话到期、IsLevel2、pid
ths rt stop     # 优雅停机（socket shutdown，兜底 SIGTERM）
```

IPC：Unix domain socket `~/.ths_sidecar.sock`（0600），行分隔 JSON：

```
{"cmd":"status"}
{"cmd":"realtime","codes":["USHA600519","USZA000977","USTM920185"]}
{"cmd":"shutdown"}
```

市场前缀实证自客户端 `Hevo.Core.Market.ParseFromOldID` 在真程序集上的
求值：17→`USHA`（沪 A）、33→`USZA`（深 A）、151→`USTM`（北交所）。
realtime 响应每行含 code/market/date_time（服务端快照请求不回该字段，
恒为 null）/latest/prev_close/open/high/low/close（盘后为 NaN→null，
收盘价由 latest 承载）/volume/amount/bid[5]/ask[5]/fields（原始字段号
字典）。

## 保活与约束

- AuthSession 约 24h：supervisor 每分钟检查，到期前 30 分钟用存量工件
  自动 re-verify 并重设 UserToken；掉线自动重 TryStart（退避在分钟级）。
- **同账号互踢**：sidecar 在线期间不要再启动真客户端 GUI 登录同一账号
  （反之亦然），否则两边会被踢线。
- DNS：本组件沿用 PoC 实证的 DnsCache 预填（静态表 + DoH 动态解析），
  因为沙箱 DNS 会把行情主机名解析到合成地址、二进制协议无响应。
- 日志 `~/.ths_sidecar.log` 中凭据一律掩码（passwd 只记长度，
  Passport/Session 不落盘）；pid 文件 `~/.ths_sidecar.pid`。
- 请求串行、低频定位：单股快照查询，不做批量订阅与推送。
