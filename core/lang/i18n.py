"""User-facing text in more than one language.

English is the source text and the dictionary key; anything without a translation falls back to English, so a missing entry never breaks a
page. Chinese is written once in Simplified (`ZH`) and Traditional is derived from it (`to_traditional`: one-to-one characters from the OpenCC
table, a few curated overrides for ambiguous characters, and a handful of Taiwan-style words).

Reply language is chosen by the USER (their UI or chat language), not by the message: someone who reads Chinese may check an English
phishing email and want the explanation in Chinese."""
from __future__ import annotations

import json
import re
from pathlib import Path

LANGS = ("en", "zh", "zh-Hant", "ms", "ta")
NAMES = {"en": "English", "zh": "简体中文", "zh-Hant": "繁體中文", "ms": "Bahasa Melayu", "ta": "தமிழ்"}
PROMPT_NAMES = {"en": "English", "zh": "Simplified Chinese (简体中文)", "zh-Hant": "Traditional Chinese (繁體中文)", "ms": "Malay (Bahasa Melayu)", "ta": "Tamil (தமிழ்)"}


def norm(lang: str | None) -> str:
    """Map anything (a cookie, an Accept-Language header, a Telegram language_code, a detected language) to one of LANGS."""
    s = (lang or "").strip().lower().replace("_", "-")
    if s in ("zh-hant", "zh-tw", "zh-hk", "zh-mo", "hant") or s.startswith("zh-hant"):
        return "zh-Hant"
    if s.startswith("zh") or s in ("cn", "chinese"):
        return "zh"
    if s == "ms" or s.startswith("ms-") or s in ("bm", "may", "malay", "bahasa", "bahasa-melayu"):
        return "ms"
    if s == "ta" or s.startswith("ta-") or s in ("tam", "tamil"):
        return "ta"
    return "en"


def from_accept_language(header: str | None) -> str:
    """First supported language in an Accept-Language header ('zh-TW,zh;q=0.9,en;q=0.8' -> 'zh-Hant'); English if none."""
    for part in (header or "").split(","):
        code = part.split(";")[0].strip()
        if code:
            n = norm(code)
            if n != "en" or code.lower().startswith("en"):
                return n
    return "en"


# ---------------------------------------------------------------------------------------------------- Simplified -> Traditional
# zh_s2t.json: OpenCC's one-to-one Simplified-to-Traditional characters (STCharacters.txt), moved to the Taiwan-standard form (TWVariants.txt).
_S2T_CHARS: dict[str, str] = json.loads((Path(__file__).parent / "data" / "zh_s2t.json").read_text(encoding="utf-8"))
_PREF = {"复": "複", "干": "幹", "里": "裡"}  # where the table's first choice is the less common reading for our texts
_PHRASES = (  # words that differ between Simplified and Traditional usage, or whose character depends on the word
    ("回复", "回覆"), ("联系", "聯繫"), ("关系", "關係"), ("短信", "簡訊"), ("软件", "軟體"), ("网络", "網路"), ("信息", "資訊"), ("视频", "影片"), ("链接", "連結"),
    ("二维码", "QR碼"), ("转账", "轉帳"), ("支付宝", "支付寶"), ("质量", "品質"), ("程序", "程式"), ("硬件", "硬體"), ("打印", "列印"), ("默认", "預設"), ("数据", "資料"),
    ("账户", "帳戶"), ("账号", "帳號"), ("干净", "乾淨"), ("后来", "後來"), ("分钟", "分鐘"), ("复制", "複製"), ("消息", "訊息"), ("反馈", "回饋"), ("刷新", "重新整理"),
)


def to_traditional(s: str) -> str:
    for a, b in _PHRASES:
        s = s.replace(a, b)
    return "".join(_PREF.get(c) or _S2T_CHARS.get(c, c) for c in s)


# ---------------------------------------------------------------------------------------------------- the dictionary
ZH: dict[str, str] = {
    # ---- verdict headlines and fixed answers
    "🚨 SCAM. Don't pay, don't tap the link.": "🚨 这是骗局。不要付款，不要点链接。",
    "⚠️ Likely a scam. Don't act on it yet.": "⚠️ 很可能是骗局。先不要照做。",
    "✅ Looks safe, but verify first.": "✅ 看起来没问题，但请先核实。",
    "❓ Not sure. Treat it with care.": "❓ 不确定，请小心对待。",
    "💛 You're not alone, and this is not your fault.": "💛 你并不孤单，这不是你的错。",
    "This looks okay, but I can't be sure. If it asks for money, codes or a rush, check first using an official number or website you already trust.":
        "这条看起来没问题，但我不能保证。如果它要钱、要验证码或催你，请先用你信得过的官方电话或网站核实。",
    "I can't be sure. If it asks for money, codes or a rush, check first using an official number or website you already trust.":
        "我无法确定。如果它要钱、要验证码或催你，请先用你信得过的官方电话或网站核实。",
    "I couldn't finish checking this message.": "我没能完成这条消息的检查。",
    "Scammers are skilled, and many smart people get fooled.": "骗子很会骗人，很多聪明人也会上当。",
    "Call your bank or card company now and tell them. Change any password you shared. Report it to your local police or consumer-fraud line. Tell someone you trust.":
        "请马上联系你的银行或信用卡公司说明情况。把你透露过的密码都改掉。向当地警方或反诈热线报案。并告诉一个你信任的人。",
    "Nothing here asks for money, codes, passwords or a rush, and I found no red flags.": "这条消息没有要钱、要验证码、要密码，也没有催你，我没发现可疑之处。",
    "Don't act on it yet. Check using a phone number or website you already trust.": "先别照做。用你信得过的电话号码或网站去核实。",
    "Don't act on it. Check using a phone number or website you already trust.": "不要照做。用你信得过的电话号码或网站去核实。",
    "I can't point to one clear giveaway, so treat it with care.": "我说不出一个明确的破绽，所以请小心对待。",
    "Nothing here asks for money, codes, passwords or a rush, so this one is fine.": "这条消息没有要钱、要验证码、要密码，也没有催你，所以它没问题。",
    # ---- evidence
    "“{q}” is a known scam phrase ({label})": "“{q}”是常见的骗局用语（{label}）",
    "The link {host} {why}": "链接 {host} {why}",
    "The link {host} goes to {brand}'s real website": "链接 {host} 指向 {brand} 的官方网站",
    "The website {host} was registered only {age} days ago": "网站 {host} 仅在 {age} 天前注册",
    "The website {host} was registered only {age} days ago (under six months)": "网站 {host} 仅在 {age} 天前注册（不到半年）",
    "The website {host} has existed for {years} years": "网站 {host} 已存在 {years} 年",
    "The website address {host} doesn't exist (any more)": "网址 {host} 不存在（或已失效）",
    "{host} points to an internal address, which a real website never does": "{host} 指向内部地址，正规网站不会这样",
    "{src} lists {host} as {org}'s website": "{src}显示 {host} 是 {org} 的网站",
    "{src} lists {site} as {org}'s website, but this link goes to {host}": "{src}显示 {site} 才是 {org} 的网站，但这个链接指向 {host}",
    "The phone number is {why}": "这个电话号码{why}",
    "an area code tied to 'one-ring' scams": "属于常见的“响一声”诈骗区号",
    "a premium-rate number that can charge you heavily": "是可能收取高额费用的增值电话",
    "a UK '070' personal number, which scammers use to look like a mobile": "是英国的“070”个人号码，骗子常用它冒充手机号",
    "The link {host} is on a public list of known phishing websites": "链接 {host} 在公开的钓鱼网站名单上",
    "The website {host} got its first security certificate only {age} days ago": "网站 {host} 的第一张安全证书仅是 {age} 天前签发的",
    "The website {host} has had security certificates on record for {years} years": "网站 {host} 的安全证书记录已有 {years} 年",
    "Asks for payment by {rail}, which can't be taken back": "要求用{rail}付款，这种方式无法追回",
    "Asks you to hand over a code that is the key to your account": "要你交出验证码，而它是你账户的钥匙",
    "Asks you to pay while rushing you": "一边催你，一边要你付款",
    "It advertises a premium-rate service (a short code, or a price per message or minute)": "它推广增值收费服务（短号码，或按条、按分钟收费）",
    "Follows the “{label}” scam script ({n} of its {m} telltale signs)": "符合“{label}”这类骗局套路（{m}个典型特征中占了{n}个）",
    "Claims to be {who} but asks for payment by {rail}. Real organisations never collect payment that way": "自称是{who}，却要求用{rail}付款。正规机构从不这样收款",
    "Claims to be {who} but asks you to share a code or password, which real organisations never ask for by message": "自称是{who}，却要你提供验证码或密码，正规机构不会通过消息索要",
    "Claims to be {who} but tells you to keep it secret": "自称是{who}，却叫你保密",
    "Says it's family and asks for money, but gives you no way to check it's really them": "自称是家人并要钱，却没有给你任何核实身份的办法",
    "It reads like the first step of a scam: an out-of-the-blue message that invites you to reply or move to another app":
        "这像是骗局的第一步：突然冒出来的消息，引你回复或转到别的App聊天",
    "Tells you to keep it secret, so you can't check with anyone": "叫你保密，让你无法找人核实",
    "The AI reviewer thinks it follows the “{label}” scam script": "AI审阅者认为它符合“{label}”骗局套路",
    "The message tries to give the checker instructions, which real messages never do": "这条消息在给检查器下指令，正常消息不会这样",
    "Web note (unverified): {note}": "网上资料（未经证实）：{note}",
    "Wants you to reply to a free email address while claiming to be an organisation or offering a prize, job or loan": "要你回复到一个免费邮箱，却自称是机构，或在给你奖品、工作或贷款",
    "Every link goes to a long-established website that exists": "所有链接都指向存在已久的正规网站",
    "It reads as a normal {label}: it informs you and asks for nothing risky": "这像是一条正常的{label}：只是通知你，没有要求任何有风险的事",
    "It asks for nothing risky: no money, codes, passwords, links or installs, and it doesn't rush you": "它没有要求任何有风险的事：不要钱、不要验证码和密码、没有链接或安装，也没有催你",
    "The AI reviewer spotted: {label}": "AI审阅者发现：{label}",
    "A second look by the AI reviewer also found nothing suspicious": "AI审阅者再看一遍，也没发现可疑之处",
    "The AI reviewer found nothing suspicious": "AI审阅者没发现可疑之处",
    "A second reviewer was worried: {concern}": "第二位审阅者有顾虑：{concern}",
    "A second reviewer looked for risk signals and found none": "第二位审阅者检查了风险信号，没有发现问题",
    # ---- why-strings returned by the link checker
    "imitates {brand} but is not {official}": "冒充 {brand}，但它并不是 {official}",
    "uses disguised (punycode) characters": "使用了伪装的字符（punycode）",
    "is a raw IP address": "只是一串IP地址",
    "is a link shortener that hides the real address": "是短链接，隐藏了真实网址",
    "ends in {tld}, common in throwaway scam sites": "以 {tld} 结尾，这是一次性骗局网站常用的后缀",
    "looks one letter away from {brand} ({official})": "和 {brand}（{official}）只差一个字母",
    "stacks words like 'secure' and 'login' that scam sites love": "堆砌了“secure”“login”这类骗局网站爱用的词",
    "has many hyphens": "含有很多连字符",
    # ---- payment rails
    "gift card": "礼品卡", "crypto": "加密货币", "wire": "电汇", "safe account": "“安全账户”",
    # ---- the answer's trace ("How I decided")
    "{n} link(s), {m} payment method(s) found": "发现 {n} 个链接、{m} 种付款方式",
    "message tries to give the checker instructions": "这条消息在给检查器下指令",
    "sounds like you may already have acted: switching to support": "听起来你可能已经照做了：转为提供支持",
    "no AI configured: using built-in rules only": "未配置AI：只用内置规则",
    "{n} red flag(s) from built-in rules": "内置规则发现 {n} 个红旗",
    "second reviewer found nothing": "第二位审阅者没发现问题",
    "tone and safety rules satisfied": "语气和安全规则均已满足",
    "internal error: returning a cautious answer": "内部出错：给出谨慎的回答",
    "added the 'verify first' caveat to a safe verdict": "在“安全”结论后加上了“请先核实”的提醒",
    "supplied a safe action": "补充了安全的做法",
    "supplied a giveaway line": "补充了一句破绽说明",
    "removed reassurance that contradicted a scam verdict": "删掉了与骗局结论矛盾的安慰话",
    "not a confident scam: kept out of training": "不是确定的骗局：不放入训练",
    "low confidence: kept out of training": "把握不高：不放入训练",
    "replaced an explanation that mentioned things not in the message": "替换了一段提到消息里没有的内容的说明",
    "in a language we do not cover yet: kept out of training": "目前还不支持这种语言：不放入训练",
    "only the model suspects it (no independent evidence): kept out of training": "只有AI怀疑它（没有独立证据）：不放入训练",
    "added to training": "已加入训练",
    "confident enough": "把握已足够",
    "nothing more to check": "没有更多可查的了",
    "nothing more any tool can answer": "已没有工具能回答的问题",
    "second look unavailable": "无法再看一遍",
    "reached the round limit ({n})": "已达到轮数上限（{n}）",
    "time budget used up": "时间用完了",
    "model-call budget used up": "AI调用次数用完了",
    # ---- the arbiter's reasons
    "hard evidence: {facts}": "确凿证据：{facts}",
    "only the AI is suspicious, and {why}": "只有AI起疑，而且{why}",
    "independent checks look reassuring": "独立检查的结果让人放心",
    "the message asks for nothing": "这条消息没有要求任何事",
    "{n} separate red flags": "{n} 个不同的红旗",
    "evidence adds up ({w:g} points against {h:g} reassuring)": "证据累积起来了（{w:g} 分不利，{h:g} 分让人放心）",
    "only the AI raised a red flag, and only once so far": "只有AI提出过红旗，而且目前只有一次",
    "1 red flag": "1 个红旗",
    "1 red flag (outweighed by reassuring facts)": "1 个红旗（被让人放心的事实抵消）",
    "model suspects a scam but gave no verifiable evidence": "AI怀疑是骗局，但拿不出可核实的证据",
    "the AI isn't sure and nothing else explains it": "AI也拿不准，其他检查也解释不了",
    "asks for something sensitive or is hard to judge": "涉及敏感要求，或者难以判断",
    "can't judge this language with built-in rules alone": "仅凭内置规则无法判断这种语言",
    "it reads like an ordinary {label}, but nothing independent confirms it, so I can't call it safe": "这看起来像一条普通的{label}，但没有独立的证据能证实，所以我不能说它安全",
    "can't fully check this language with built-in rules, so I can't call it safe": "内置规则无法完整检查这种语言，所以我不能说它是安全的",
    "contains a link that can't be verified": "含有无法核实的链接",
    "built-in rules alone can't vouch that a message is safe": "只靠内置规则，无法担保一条消息安全",
    "asks for nothing risky and no red flags found": "没有要求有风险的事，也没发现红旗",
    "only the AI raised these flags, so 'likely' rather than 'scam'": "这些红旗只有AI提出，所以判为“很可能”而不是“骗局”",
    "message tries to instruct the checker": "这条消息试图给检查器下指令",
    "second opinion: {concern}": "第二意见：{concern}",
    # ---- who produced a piece of evidence, and how it counts (used by the page)
    "Red flag": "红旗", "Reassuring": "让人放心", "Note": "备注",
    "Known pattern": "已知模式", "What it asks": "它要求什么", "Checked": "已核查", "AI reviewer": "AI审阅者",
    "weak": "弱", "medium": "中", "strong": "强", "counts for less": "分量较轻",
    # ---- purposes (labels shown in evidence)
    "casual chat": "日常聊天", "appointment or booking": "预约或预订", "delivery update": "物流或配送通知", "payment or account alert": "支付或账户提醒", "login code": "登录验证码",
    "account notice": "账户通知", "work, school or club logistics": "工作、学校或社团通知", "invoice or bill": "发票或账单", "advert or offer": "广告或优惠",
    "request for money": "要钱", "request for a code, password or personal detail": "索要验证码、密码或个人信息", "request to install an app or allow access": "要求安装软件或开放权限",
    "prize, reward or refund to claim": "要你领取的奖品、奖励或退款", "job, loan or investment offer": "兼职、贷款或投资邀约", "urgent warning about a problem": "关于问题的紧急警告",
    "out-of-the-blue first contact": "突然的陌生联系", "emergency or emotional appeal": "紧急情况或感情诉求", "request to call a number": "要你回电", "something else": "其他",
    # ---- scam scripts (labels)
    "Parcel fee": "包裹费用", "Bank security alert": "银行安全警报", "Family emergency": "亲人紧急情况", "Tech support": "技术支持", "Romance / trust": "感情/信任",
    "Fake investment": "虚假投资", "Fake job / tasks": "虚假兼职/任务", "Prize / lottery": "中奖/抽奖", "Tax / government threat": "税务/政府威胁",
    "Subscription / purchase call-back": "订阅/订单回电", "Billing update link": "账单更新链接", "Accidental payment": "误转账", "Inheritance / loan fee": "遗产/贷款费用",
    "Account verification": "账号验证", "Overdue bill": "逾期账单", "Boss asks for gift cards": "“老板”要礼品卡", "Marketplace code request": "二手平台验证码",
    "Cheque / refund-the-difference": "支票/退差价", "Rental deposit": "租房押金", "Government rebate / refund": "政府退款/补贴", "Ticket pre-payment": "门票预付",
    "Charity appeal": "慈善募捐", "Approved claim / loan": "已批准的理赔/贷款", "Warranty call-back": "保修回电", "Fake customer-service refund": "假客服退款",
    "Fake loan or credit-limit offer": "假贷款/提额", "Friendship that turns into an investment pitch": "交友变投资推销",
}

from core.lang.i18n_bot import BOT_ZH  # noqa: E402  (website, game and bot strings live in their own files)
from core.lang.i18n_inputs import INPUTS_ZH  # noqa: E402
from core.lang.i18n_ms import MS, TACTICS_MS  # noqa: E402  (Malay: Latin script, so no Simplified/Traditional step)
from core.lang.i18n_ui import UI_ZH  # noqa: E402
from core.lang.i18n_social import SOCIAL_MS, SOCIAL_ZH  # noqa: E402
from core.lang.i18n_ta import TA, TACTICS_TA  # noqa: E402  (Tamil: its own script, so no Simplified/Traditional step)

ZH.update(UI_ZH)
ZH.update(BOT_ZH)
ZH.update(INPUTS_ZH)
ZH.update(SOCIAL_ZH)
MS.update(SOCIAL_MS)

TACTICS_ZH = {
    "urgency-pressure": {"label": "催你马上行动", "blurb": "他们说你必须立刻行动，让你来不及多想。", "tell": "正规公司会给你时间。只给几个小时的期限，是施压的手段。",
                         "action": "先停下来，不要回复也不要付款。用你自己知道的电话号码去核实。"},
    "authority-spoofing": {"label": "冒充权威", "blurb": "他们自称是警察、银行或公司，让你听话。", "tell": "真正的官方人员不会让你保密，也不会让你转移资金。",
                           "action": "挂断或不理会。自己查到官方电话，再打过去确认。"},
    "otp-credential-phish": {"label": "索要验证码或密码", "blurb": "他们想要发到你手机上的验证码、密码或PIN。", "tell": "没有任何正规机构需要你的验证码，它是你账户的钥匙。",
                             "action": "绝不告诉别人验证码。自己打开官方App或网站登录。"},
    "irreversible-payment": {"label": "礼品卡、加密货币或汇款", "blurb": "他们要求你用无法追回的方式付款。", "tell": "礼品卡、加密货币和电汇是骗子收钱的方式，正规账单从不这样收款。",
                             "action": "不要付款。用这种方式转出的钱几乎追不回来。"},
    "lookalike-link": {"label": "假网址", "blurb": "链接看起来像正规公司的，但网址有细微差别。",
                       "tell": "仔细读网址。正规公司的网址以它自己的名字结尾，比如 amazon.com。多出的单词或奇怪的结尾都是假的。", "action": "不要点链接。自己输入官方网址，或打开官方App。"},
    "too-good-to-be-true": {"label": "好得不真实", "blurb": "奖品、暴利或轻松赚钱，却没有任何条件。", "tell": "你没参加过的抽奖却中奖了，那就是诱饵。", "action": "忽略它。没参加过的活动不可能中奖。"},
    "emotional-manipulation": {"label": "拿感情做文章", "blurb": "亲人出事、恋爱，或用威胁吓你。", "tell": "他们利用恐惧或感情，让你来不及思考，还会叫你别打电话核实。",
                               "action": "先冷静。用你已有的号码打给本人，问一个只有对方才知道的问题。"},
    "remote-access-request": {"label": "要求控制你的电脑", "blurb": "他们让你安装软件，说是帮你“修理”问题。", "tell": "正规客服不会主动联系你，更不会让你安装远程控制软件。",
                              "action": "什么都不要安装。挂断电话。如果已经装了，先断网，再联系银行。"},
    "advance-fee": {"label": "先交费用", "blurb": "想拿到钱、贷款或奖品，必须先交一笔“小费用”。", "tell": "真正的奖品和贷款，不会要你先付钱。", "action": "不要交费。根本没有钱在等你。"},
    "impersonation-official": {"label": "冒充机构或公司", "blurb": "一条伪装成税务局、医保、快递或银行的消息。", "tell": "官方机构会寄信，不会发短信让你点链接付款或“确认”信息。",
                               "action": "忽略它。通过官方网站或银行卡背面的电话联系对方。"},
    "investment-crypto": {"label": "虚假投资", "blurb": "声称“稳赚”的投资，常常和加密货币有关。", "tell": "承诺高回报、催你入金，都是假投资的特征。", "action": "不要转钱。先和信得过的人商量，再决定要不要投资。"},
    "job-task-scam": {"label": "虚假兼职或刷单", "blurb": "轻松在线工作，却要你先充值才能“解锁”报酬。", "tell": "真正的工作是公司付钱给你，不会让你先垫付或充值。", "action": "马上离开，不要为任何工作垫付一分钱。"},
}

# a "why" string from the link checker that carries values: pattern -> template key
_WHY_PATTERNS = (
    (re.compile(r"^imitates (?P<brand>.+) but is not (?P<official>.+)$"), "imitates {brand} but is not {official}"),
    (re.compile(r"^ends in (?P<tld>\S+), common in throwaway scam sites$"), "ends in {tld}, common in throwaway scam sites"),
    (re.compile(r"^looks one letter away from (?P<brand>\S+) \((?P<official>[^)]+)\)$"), "looks one letter away from {brand} ({official})"),
)


def tr(text: str, lang: str = "en", **kw) -> str:
    """Translate an English template and fill it in. Unknown text and unknown languages fall back to English."""
    lang = norm(lang)
    out = text
    if lang == "ms":
        out = MS.get(text, text)
    elif lang == "ta":
        out = TA.get(text, text)
    elif lang != "en":
        z = ZH.get(text)
        if z is not None:
            out = to_traditional(z) if lang == "zh-Hant" else z
    return out.format(**kw) if kw else out


def tactic_text(tid: str, field: str, lang: str, english: dict) -> str:
    """label | blurb | tell | action of a tactic in the reply language (English comes from tactics.TACTICS)."""
    lang = norm(lang)
    if lang == "en":
        return english[tid][field]
    if lang == "ms":
        return TACTICS_MS.get(tid, {}).get(field) or english[tid][field]
    if lang == "ta":
        return TACTICS_TA.get(tid, {}).get(field) or english[tid][field]
    z = TACTICS_ZH.get(tid, {}).get(field)
    if z is None:
        return english[tid][field]
    return to_traditional(z) if lang == "zh-Hant" else z


def why(text: str, lang: str) -> str:
    """Translate one link-checker finding ('imitates dhl but is not dhl.com')."""
    if norm(lang) == "en":
        return text
    for rx, key in _WHY_PATTERNS:
        if m := rx.match(text):
            return tr(key, lang, **m.groupdict())
    return tr(text, lang)
