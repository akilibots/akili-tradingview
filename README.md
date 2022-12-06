# akili-tradingview

  
[![stability-alpha](https://img.shields.io/badge/stability-alpha-f4d03f.svg)](https://github.com/mkenney/software-guides/blob/master/STABILITY-BADGES.md#alpha)
[![Telegram](https://badges.aleen42.com/src/telegram.svg)](https://t.me/+9F0CZj8emLc2YTY0)

  

akili-tradingview is a bot that provides an interface from TradingView into DyDx. This allows alarms set on trading view to trigger orders on DyDx opening possibilities such as channel, wedge, etc. and will support anything that a TradingView alarm can be set to.

![Sample Channel Using akili-tradingview](https://raw.githubusercontent.com/akili-bots/.github/main/images/channel.png)

Example use of this bot with trading view, longing on the bottom line and shorting on the top line as the price bounces within the channel. I extended the channel slowly everyday until the price dips on the last short. The bot two trend lines are set to reset each other and fire only once.

Again this bot is non opinionated, so be careful with any alarms that are not set to fire only once. Also please please please do not remove the ALLOWED_IPs from the code. These are set to allow only signals from TradingView's IP addresses. Signals are not authenticated (for now) so if you open this up anyone anywhere with your IP address and port and who has read this can send signals to your bot.

If you don't have an DyDx account, here's my affiliate link to DyDx for a 40% discount. I'd appreciate https://dydx.exchange/r/JUDCLWBC
If you also don't have a TradingView account, please use my affiliate link for a 30% discount. Thank you. https://www.tradingview.com/gopro/?share_your_love=availableEggs79157 

## Configuring the bot
The bot picks up its configuration from an environment variable called config or a file named config.json under the config folder. More examples to follow how to use Docker to achieve this. A sample file is stored in the config folder that contains all options required.

Place the name of the bot in the "name" section. This name is displayed before each message on Telegram (if integrated) and when logging. Helps differentiate which bot is doing what especially when all the bots are sending their output to the same Telegram user.

```
"main":  {
	"name":  "TV📺",
},
```

The dydx section contains all the blockchain details of your dydx account. Instructions on how to set up your DyDx settings on the bot can be found here https://github.com/akili-bots/.github/tree/main/profile
```
"dydx":  {
	"APIkey":  "put your dydx API key here",
	"APIsecret":  "put your dydx API secret here",
	"APIpassphrase":  "put your dydx passphrase here",
	"stark_private_key":  "put your stark private key here",
	"default_ethereum_address":  "put your eth wallet address used in dydx here"
}
```
Next is the Telegram section. To use, create a Telegram bot and input it's bot token and your chat id below.
```
"telegram":  {
	"chatid":  "",
	"bottoken":  ""
}
```

By using variables in the alert you can come up with very interesting scenarios for your start and stop triggers. https://www.tradingview.com/support/solutions/43000531021-how-to-use-a-variable-value-in-alert/
