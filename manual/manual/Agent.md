# MaaFw Agent Guide

&emsp;&emsp;本篇手册将讲述本项目的MaaFw Agent部分的设计、使用说明。当前的MaaGFL Agent实现了如下的功能：

1. 外部通知接口；
2. Key的Win32API输入。

## 一、外部通知

&emsp;&emsp;Agent目前以Custom Action的方式实现了**Telegram Bot**、**企业微信群通知**两个外部通知API。其均定义在`agent/action/log.py`中。同时提供了如下的两个单独的Python测试脚本：

1. `tools/notification/telegram.py`
2. `tools/notification/wechat.py`

如要使用这两项外部通知，请按照下一小节中的内容搭建外部通知环境，并通过上述两项脚本确认其正常接收消息。

### 1.1 环境搭建

#### 1.1.1 Telegram Bot

1. 首先在电报的`BotFather`中通过`/start`激活该Bot；
2. 使用命令`/newbot`来创建机器人，接着为其配置用户名、名称等；
3. 在完成(2)后取得该机器人的Token；
4. 向该机器人发送一条消息（即，创建一个对话）
5. 通过`tools/notification/telegram.py`发送消息测试，该脚本将以最新的对话作为ChatID；
6. 确认在Telegram上收到了机器人发送的消息，即我们在(5)中发送的内容。

如此，我们变得到了`Bot_Token`和`Chat_ID`两个内容，这两项内容将作为MaaFW的外部通知参数使用。为安全性，请勿向他人泄露这两项数据。

额外的，`Token`和`Chat ID`格式如下：

```sh
# Token
1234567890:AAEC_WfYcYFVrPEMILisj60VeLVlkjvtoI8
# Chat ID
5049126023
```

#### 1.1.2 Wechat

1. 首先创建一个企业微信的群聊天（如果人数不足，则创建两个Bot将其邀请到群聊中）；
2. 在群聊天中找到**消息推送**，选择添加一个消息推送，这里我们需要填入名称、描述等；
3. 我们完成(2)后，将获得一个`Webhook`，这里我们将其保存并记录；
4. 通过`tools/notification/wechat.py`向微信群通知发送消息，确认其正常工作；
5. 查看企业微信群，确认收到了我们在(4)中发送的内容。

如此，我们变得到了`Webhook`，这项内容将作为MaaFw的外部通知参数使用。为安全性，请勿向他人泄露这项数据。

额外的，`Webhook`格式如下：

```sh
# Webhook
066hj7e3-891b-4b3a-acd5-8a874876hsf9
```

### 1.2 Agent配置

&emsp;&emsp;在`agent/agent.conf`中有如下配置：

```conf
########## Section I : 外部通知 ##########

# Wechat || Telegram
Default_ExtNotify=Wechat

# Telegram Bot Token
Bot_Token=
# Telegram Chat ID
Chat_ID=
# Wechat Bot Webhook
Webhook_Key=
```

其中：

1. `Default_ExtNotify`用于指定外部通知接口，可以填入`Telegram`或`Wechat`；
2. `Bot_Token`为Telegram Bot Token，可以不填；
3. `Chat_ID`为Telegram Bot与你账号直接的Chat ID，可以不填；
4. `Webhook_Key`为企业微信群通知的Webhook，可以不填。

### 1.3 开发相关

&emsp;&emsp;本小节将介绍编写MaaFw Pipeline中提供的Custom Action，以方便开发人员使用。

&emsp;&emsp;外部通知目前均使用一套模板化的配置：

1. `parametric_log`，将消息输出到终端（如启用GUI则是右侧日志区）；
2. `parametric_telegram`，将消息输出到Telegram（需要配置Bot_Token和Chat_ID）；
3. `parametric_wechat`，将消息输出到企业微信群通知（需要配置Webhook）；
4. `parametric_extnotify`，根据用户`Default_ExtNotify`中的选择将消息推送到电报或微信。

上述4个Action均以如此的形式调用：

```json
"Notify_Default_Node": {
    "recognition": "DirectHit",
    "action": "Custom",
    "custom_action": "parametric_extnotify",
    "custom_action_param": {
        "type": "info",
        "message": "默认外部消息通知接口：{status}，当前次数：{count}",
        "parameters": {
            "status": "正常",
            "count": "{increment_Task_Counter}"
        }
    },
    "pre_delay": 100,
    "post_delay": 100
}
```

其中：

1. `custom_action`可以替换为任意的`parametric_*`；
2. `type`用于指定日志等级，目前只实现了Info和Debug；
3. `message`为传出的消息，通过`parameters`进行参数化配置；
4. `increment_Task_Counter`目前在Python中编写了一个计数器，每调用一次`count`将增加`1`。