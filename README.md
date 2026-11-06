# Web3 Radar

长期运行的美元稳定币理财利率监控器。当前第一阶段每小时采集 Binance、OKX、Bitget、Bybit 的活期/定期 Earn 产品，保留历史快照，并发送到 Telegram 群聊。

它不会只转发平台展示的最高利率。对于阶梯利率，会同时展示：

- 小资金 Bonus 档位的金额上限；
- 超出 Bonus 上限后的基础利率；
- 新用户、VIP、地区等资格限制；
- 定期期限、起投额、个人上限和售罄状态。

## 数据覆盖

| 交易所 | 活期 | 定期 | 小额 Bonus | 凭据要求 |
|---|---:|---:|---:|---|
| Binance | 是 | 是 | 阶梯金额与基础利率 | 活期可公开读取；定期需只读 Key |
| OKX | 是 | 官网可见产品 | Bonus 描述；若官网未给额度则明确不猜测 | 无 |
| Bitget | 是 | 是 | 完整 `apyList` 阶梯 | 需只读 Key、Secret、Passphrase |
| Bybit | 是 | 是 | `tierAprDetails`、限定用户、VIP | 无 |

任何一家失败都不会阻断其他三家。错误会入库并出现在 Telegram 对应交易所的消息底部。

## 本地首次运行

需要 Python 3.11 或更高版本，不依赖第三方 Python 包。

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

1. 从 `@BotFather` 创建 Telegram Bot，将 Bot 拉入目标群聊；
2. 填写 `TELEGRAM_BOT_TOKEN` 和群聊的 `TELEGRAM_CHAT_ID`；
3. 如需 Binance 定期和 Bitget 完整产品，创建**仅查询/只读** API Key。不要开启交易或提现权限；
4. 可在 `STABLECOINS` 调整监控币种。

先做不发送消息的真实采集：

```powershell
python -m web3_radar run --once --dry-run
```

确认输出后发送一次：

```powershell
python -m web3_radar run --once
```

常驻运行：

```powershell
python -m web3_radar run
```

## Docker 服务器部署

将 `.env.example` 复制为 `.env` 并填写凭据，然后：

```bash
docker compose up -d --build
docker compose logs -f radar
```

容器会立即采集一次，之后按 `MONITOR_INTERVAL_SECONDS`（默认 3600 秒）运行。SQLite 历史数据库和健康状态保存在宿主机的 `./data`。容器带健康检查；最近成功采集过旧或上次运行失败时会变为 unhealthy。

## 命令

```text
python -m web3_radar run                 # 每小时运行并发送
python -m web3_radar run --once          # 发送一次后退出
python -m web3_radar run --once --dry-run # 采集、入库、打印，不发 Telegram
python -m web3_radar healthcheck         # 检查最近运行状态
python -m unittest discover -s tests -v  # 运行测试
```

## 数据与安全

- `.env`、`data/` 和数据库不会进入 Git；
- 交易所 Secret 和 Telegram Token 只从环境变量读取，不写入日志或 SQLite；
- 监控器只发送 GET 查询，不包含申购、赎回、交易或转账代码；
- Binance 与 Bitget Key 请绑定服务器出口 IP，并仅授予读取权限；
- OKX 官网产品接口属于网页接口，可能变更；适配器故障时会明确报警，正式公共市场利率仍独立采集。

## 官方接口参考

- [Binance Simple Earn](https://developers.binance.com/en/docs/products/simple-earn)
- [OKX API v5](https://www.okx.com/docs-v5/en/)
- [Bitget Savings Product List](https://www.bitget.com/legacy-docs/classic/earn/savings/Savings-Products)
- [Bybit Earn Product Info](https://bybit-exchange.github.io/docs/v5/finance/earn/easy-onchain/product-info)
- [Bybit Fixed Saving](https://bybit-exchange.github.io/docs/v5/finance/earn/fixed-saving/product)

利率是动态数据，不代表承诺收益；这些产品也不是受存款保险保护的银行存款。
