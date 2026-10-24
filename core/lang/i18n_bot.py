"""Chinese (Simplified) text for the Telegram bot: English text -> Simplified Chinese. Merged into core.lang.i18n.ZH."""

BOT_ZH: dict[str, str] = {
    "Hi! I'm Finn 🐟, Baitproof's scam-spotting fish. I never take the bait!\n\nForward or paste any message you're unsure about and I'll tell you if it's a scam, show you the one giveaway, and add that trick to your practice.\n"
    "You can also send a screenshot or a voice note.\n\n"
    "/quiz is a quick game: scam or not? (/quiz daily is today's Daily Challenge.)\n"
    "/challenge makes a link to send your family, to see if they can spot the scam too.\n\n"
    "/link CODE connects this chat to your Baitproof web profile, so everything you check here shows up in your records.\n"
    "/history shows your latest checks, /score your Baitproof score, /unlink disconnects.\n"
    "/report shows who to call, and where to report a scam, if you have already paid or shared something.\n"
    "/family lets someone you trust get a short note when you meet a scam (they never see your messages). /safeword explains a simple trick against fake \"it's me\" messages.\n"
    "/lang chooses the language: /lang en, /lang ms (Bahasa Melayu), /lang ta (தமிழ்), /lang zh (简体中文) or /lang zh-Hant (繁體中文).\n"
    "I keep the tricks I see, not your messages.":
        "你好！我是 Finn 🐟，Baitproof 的识骗小鱼。我才不会上钩呢！\n\n把你拿不准的消息转发或粘贴给我，我会告诉你是不是骗局，指出最关键的一个破绽，并把这种套路加入你的练习。\n"
        "你也可以直接发截图或语音消息给我。\n\n"
        "/quiz 是个快速小游戏：是不是骗局？（/quiz daily 是今天的每日挑战。）\n"
        "/challenge 会生成一个链接，发给家人，看看他们能不能也识破骗局。\n\n"
        "/link 验证码：把这个聊天和你的 Baitproof 网站账号连起来，这里检查的内容都会出现在你的记录里。\n"
        "/history 查看最近的检查，/score 查看你的 Baitproof 分数，/unlink 断开连接。\n"
        "/report 告诉你如果已经付钱或透露了资料，该打给谁、到哪里举报。\n"
        "/family 让你信任的人在你遇到骗局时收到一条简短提醒（他们看不到你的消息）。/safeword 介绍对付“是我啦”假消息的小窍门。\n"
        "/lang 选择语言：/lang en、/lang ms（马来文）、/lang ta（泰米尔文）、/lang zh（简体中文）或 /lang zh-Hant（繁體中文）。\n"
        "我只记住套路，不记住你的消息。",
    "Send me the message you want checked. 🐟": "请把你想检查的消息发给我。🐟",
    "The giveaway: {tell}": "破绽：{tell}",
    "What to do: {action}": "该怎么做：{action}",
    "📚 Added to your practice: {tricks}": "📚 已加入你的练习：{tricks}",
    "🗂 Saved to your records: {url}": "🗂 已保存到你的记录：{url}",
    "Send /link followed by the 6-character code from the Records page on Baitproof, for example /link K7M2QX.": "请发送 /link 加上 Baitproof 网站“记录”页面上的6位代码，例如 /link K7M2QX。",
    "Too many tries. Please wait a few minutes and get a fresh code from the website.": "尝试次数太多了。请等几分钟，再到网站上获取新的代码。",
    "That code didn't work. It may have expired (they last 10 minutes) or been used already. Get a fresh one from the Records page.": "这个代码不能用。可能已过期（有效期10分钟）或已经用过。请到“记录”页面获取新的。",
    "✅ Linked! Everything you check here now shows up in your Baitproof records, and the tricks you meet go into your practice.": "✅ 已连接！你在这里检查的内容现在都会出现在 Baitproof 记录里，遇到的套路也会加入你的练习。",
    "See them: {url}": "查看记录：{url}",
    "Disconnected. Your records stay in your Baitproof profile.": "已断开连接。你的记录仍保留在 Baitproof 账号里。",
    "This chat wasn't linked.": "这个聊天没有连接过。",
    "No checks yet. Paste or forward a message and I'll check it.": "还没有检查记录。粘贴或转发一条消息给我，我来检查。",
    "Your latest checks:": "你最近的检查：",
    "{icon} {date} via {channel}: {what}": "{icon} {date}（{channel}）：{what}",
    "All of them: {url}": "全部记录：{url}",
    "Your Baitproof score: {score}/100": "你的 Baitproof 分数：{score}/100",
    "Weakest tricks: {tricks}": "最容易上当的套路：{tricks}",
    "{n} trick(s) due for a refresher.": "有 {n} 种套路该复习了。",
    "Practise here: {url}": "在这里练习：{url}",
    "🐟 Psst! {n} scam trick(s) are due for a one-minute refresher.": "🐟 嘘！有 {n} 种骗局套路该花一分钟复习了。",
    "Language set to English.": "已切换为简体中文。",
    "Send /lang en, /lang ms, /lang ta, /lang zh or /lang zh-Hant.": "请发送 /lang en、/lang ms、/lang ta、/lang zh 或 /lang zh-Hant。",
    "telegram": "Telegram", "web": "网站",
    # ---- quiz and family challenge (the rest of the game's wording is reused from i18n_ui.py)
    "Quick quiz": "快速测验",
    "Challenge my family": "挑战我的家人",
    "“Check first” means you'd phone the sender on a number you already trust.": "“先核实”是指你会用自己已有的号码打电话给对方确认。",
    "Why it's fine: {tell}": "为什么没问题：{tell}",
    "That quiz expired. Send /quiz to start a new one.": "这个测验已过期。发送 /quiz 开始新的一局。",
    "Sorry, I didn't understand that button.": "抱歉，我不明白这个按钮。",
    "You're playing fast! Please wait a few minutes before starting another quiz.": "你玩得太快啦！请等几分钟，再开始新的测验。",
    "You've made a few challenges already. Please wait a bit before making another one.": "你已经创建了好几个挑战了。请稍等一会儿，再创建新的。",
    "The family challenge needs a web address, but BAITPROOF_URL isn't set on this bot yet. Please ask whoever runs it to set it.":
        "家人挑战需要一个网址，但这个机器人还没有设置 BAITPROOF_URL。请让运营这个机器人的人设置一下。",
    "Here's your family challenge. Forward the next message to a parent, grandparent or friend 👇": "这是你的家人挑战。把下面这条消息转发给爸爸妈妈、爷爷奶奶或朋友吧 👇",
    "Can you spot the scam? 🕵️ It takes 2 minutes and needs no account: {url}\nScammers go after families like ours, so I'd feel better if you tried it. 🛡️":
        "你能识破骗局吗？🕵️ 只要2分钟，不用注册：{url}\n骗子专挑我们这样的家庭下手，你试一下我才放心。🛡️",
    # ---- screenshots, voice notes and the links report (the reader's own messages and notes live in i18n_inputs.py)
    "📷 I read this from your screenshot:": "📷 我从你的截图里读到：",
    "🎙️ I heard:": "🎙️ 我听到的是：",
    "From: {sender}": "发件人：{sender}",
    "QR code in the picture: {url}": "图片里的二维码链接：{url}",
    "The picture was hard to read, so please check this matches what you see.": "这张图片不太清楚，请核对上面的内容和你看到的是否一致。",
    "I haven't checked it yet. Please send a clearer picture, or paste the text.": "我还没有检查。请发一张更清晰的图片，或者直接粘贴文字。",
    "I couldn't find any words in that picture. Please send a clearer one, or paste the text.": "我在这张图片里没有找到文字。请发一张更清晰的，或者直接粘贴文字。",
    "I couldn't hear any words in that voice note. Please try again, or send the text.": "我没有在这条语音里听到文字。请再试一次，或者直接发文字。",
    "That picture is too big (the limit is {mb} MB). Please send a smaller one, or paste the text.": "这张图片太大了（上限 {mb} MB）。请发一张小一点的，或者直接粘贴文字。",
    "That voice note is too big (the limit is {mb} MB). Please send a shorter one, or the text.": "这条语音太大了（上限 {mb} MB）。请发一条短一点的，或者直接发文字。",
    "That voice note is too long (the limit is {n} seconds). Please send a shorter one, or the text.": "这条语音太长了（上限 {n} 秒）。请发一条短一点的，或者直接发文字。",
    "You've sent a lot of pictures. Please wait a while, or paste the text instead.": "你发了好多图片了。请稍等一会儿，或者直接粘贴文字。",
    "You've sent a lot of voice notes. Please wait a while, or send the text instead.": "你发了好多语音了。请稍等一会儿，或者直接发文字。",
    "Sorry, I couldn't read that. Please send the text.": "抱歉，我没能读懂这个。请把文字发给我。",
    "🔗 Links": "🔗 链接",
    "→ really goes to {host}": "→ 实际指向 {host}",
    "…and {n} more link(s)": "…还有 {n} 个链接",
    "A family member": "一位家人",
    "a family member": "一位家人",
    "Someone you invited": "你邀请的人",
    "them": "对方",
    "🚨 {who} may have already paid or shared something with a scammer. Please call them now. If money was sent, they should call their bank straight away. More: /report": "🚨 {who} 可能已经向骗子付了钱或透露了资料。请马上打电话给对方。如果已经汇款，请对方立刻联系银行。更多：/report",
    "👪 {who} just checked a message that looks like a scam.": "👪 {who} 刚检查了一条看起来像骗局的消息。",
    "Tricks: {tricks}.": "套路：{tricks}。",
    "Why not give them a call, to check they're okay and haven't paid or shared anything? Tip: agree a family safe word (/safeword).": "不如打个电话给对方，确认他们没事，也没有付钱或透露资料？小提示：和家人约定一个暗号（/safeword）。",
    "You will no longer get family alerts about {who}.": "你不会再收到关于 {who} 的家人提醒了。",
    "Done. Nobody gets alerts about your checks any more.": "好了。现在没有人会收到你检查结果的提醒。",
    "Nobody was getting alerts about your checks.": "本来就没有人收到你检查结果的提醒。",
    "👪 Family alerts\n\nAsk someone you trust to send me this in their own chat (it works for 10 minutes):\n\n/guard {code}\n\nThen, when you check a message that looks like a scam, they get a short note that you checked one and which tricks it uses. They never see your messages. Stop it any time with /family off.": "👪 家人提醒\n\n请让你信任的人在他们自己的聊天里把这条发给我（10分钟内有效）：\n\n/guard {code}\n\n之后，当你检查到看起来像骗局的消息，他们会收到一条简短提醒：你检查了一条，以及它用了哪些套路。他们永远看不到你的消息内容。随时可以用 /family off 关掉。",
    "Right now {n} family helper(s) get these alerts.": "目前有 {n} 位家人帮手会收到这些提醒。",
    "Done. You won't get family alerts any more.": "好了。你不会再收到家人提醒了。",
    "You weren't getting any family alerts.": "你本来就没有收到任何家人提醒。",
    "Send /guard followed by the 6-character code your family member got from /family, for example /guard K7M2QX. To stop getting alerts: /guard off.": "请发送 /guard 加上你的家人用 /family 得到的6位代码，例如 /guard K7M2QX。想停止接收提醒：/guard off。",
    "That code didn't work. It may have expired (they last 10 minutes), been used already, or this person already has the most helpers. Ask them for a fresh one with /family.": "这个代码没有用。可能已过期（10分钟有效）、已被使用，或对方的帮手人数已满。请让对方用 /family 重新生成一个。",
    "👪 {who} is now a family helper: they get a short note when you check something that looks like a scam, never your messages. Stop it any time with /family off.": "👪 {who} 现在是你的家人帮手：你检查到看起来像骗局的消息时，他们会收到一条简短提醒，但看不到你的消息内容。随时可用 /family off 关掉。",
    "👪 You're now a family helper for {name}. When they check a message that looks like a scam, I'll tell you, so you can give them a call. I never pass on what their messages say. To stop: /guard off.": "👪 你现在是 {name} 的家人帮手。当对方检查到看起来像骗局的消息时，我会通知你，你就可以打电话给他们。我绝不会转述对方消息的内容。想停止：/guard off。",
    "🔑 A family safe word\n\nScammers copy voices and hijack chat accounts, so \"Hi Mum, it's me, I need money now\" can look and sound real. Agree ONE secret word with your family, in person. If anyone asks for money or codes in a hurry, even if it sounds just like them, ask for the safe word. No word, no money.\n\nNever type your safe word here, or in any chat.": "🔑 家人暗号\n\n骗子会模仿声音、盗用聊天账号，所以“妈，是我，我急需用钱”可能看起来、听起来都很真。请当面和家人约定一个只有你们知道的暗号。如果有人急着要钱或要验证码，哪怕听起来很像家人，也请他说出暗号。没有暗号，就不汇款。\n\n千万不要在这里或任何聊天里输入你的暗号。",
}
