"""Held-out labeled messages, written independently of data/seeds/en.json (different wording and tricks).
SCAMS must never come back SAFE. LEGIT must never come back SCAM/LIKELY (a false alarm); UNSURE is acceptable."""

SCAMS = [
    ("Hey it's me, new number. Dropped my phone in the lake lol. Can you pay my landlord $1,150 today? I'll pay you back Friday, promise", "emotional/pay"),
    ("USPS: We could not deliver your package due to an incomplete address. Update it here: usps-redelivery.top/addr", "lookalike"),
    ("Final notice: your car warranty is about to expire. Press 1 to speak to an agent before the offer ends.", "pressure"),
    ("Dear customer, your Chase card has been locked. Verify your card number and PIN at chase-secure-login.com to unlock.", "credential"),
    ("Hi Grandpa, I got arrested after an accident and need bail money. Please don't tell Dad. A lawyer will call you, wire the money right now.", "emotional/wire"),
    ("Your Apple ID was used to buy a $899 item. If this wasn't you call 1-800-555-0142 immediately and we will refund you via gift cards.", "gift"),
    ("Congrats!! You won a $500 Walmart voucher. Tap to claim before midnight: bit.ly/3xYzAbC", "prize/shortener"),
    ("Hello, I'm Mr. Okafor, a banker. A client died with no heirs and $8.2 million is unclaimed. Be my partner and we split it, I only need your bank details.", "advance"),
    ("Sir, your Aadhaar will be blocked today. Share the OTP you receive to complete re-KYC immediately.", "otp"),
    ("We detected a problem with your router. Please download TeamViewer so our engineer can fix your internet.", "remote"),
    ("I'm an army doctor deployed overseas and lonely. I'd like to know you better. I need $600 for leave papers, send via bitcoin.", "romance"),
    ("PayPal: unusual activity. Log in to confirm your identity: paypa1-support.net/login", "lookalike"),
    ("Join our VIP Telegram: our AI bot gives 5x returns every week, no risk. Deposit USDT to the wallet below to begin.", "invest"),
    ("Amazon job offer: earn $150 per day reviewing products. You must first top up $100 to your task account to unlock orders.", "job"),
    ("Your Social Security number has been suspended due to suspicious activity. Call now to avoid arrest.", "authority/pressure"),
    ("Su cuenta bancaria ha sido bloqueada. Envíe el código de 6 dígitos que recibió por SMS para desbloquearla ahora mismo.", "otp-es"),
    ("您的快递被扣留，请在24小时内支付3元关税：post-tax-pay.xyz/cn", "lookalike-zh"),
    ("Mom I lost my wallet and can't get home. Send $200 to my friend's account right now please, hurry", "emotional/pay"),
    ("IRS final demand: pay $2,340 in back taxes by buying Google Play cards or officers will be sent to your home today.", "gift"),
    ("Hi! Your electricity bill is overdue. Pay now with the link to avoid a disconnection today: pay-power-bill.click", "pressure/link"),
    ("Refund pending: Netflix overcharged you. Install the QuickSupport app so the billing agent can return your $200.", "remote"),
    ("Free government grant of $9,000 approved for you. A $120 processing fee is required before release.", "advance"),
    ("This is the fraud department of your bank. Move your balance to a secure account at once; do not speak to branch staff.", "authority/safe-acct"),
    ("Hello dear, I am sending you a package of gifts. To clear customs please pay $75 by Western Union.", "advance/wire"),
]

LEGIT = [
    "Hi Dad, can you transfer me $50 for groceries? I'll pay you back at the weekend. Thanks!",
    "Your table for 4 at Luigi's is confirmed for Friday 7pm. Reply CANCEL to cancel.",
    "Reminder: your dentist appointment is Tuesday at 3pm. Please call the office if you need to reschedule.",
    "Hey, are we still on for coffee tomorrow at 10? I'll be at the usual place.",
    "Your package from the local bookshop was delivered to your front door at 2:14pm.",
    "Happy birthday! Hope you have a wonderful day, dinner is on me tonight.",
    "Your monthly electricity statement is available in your online account. Log in through the app you already have.",
    "Don't forget the school trip form is due Friday. Thanks, Ms. Alvarez.",
    "Your verification code is 771204. It expires in 10 minutes. Never share this code.",
    "Can you pick up the kids at 4? I'm stuck in a meeting and will be home by 6.",
    "The plumber is coming Thursday between 9 and 12. Please make sure someone is home.",
    "Grandma, I'm bringing the kids on Sunday. Do you want me to pick up anything from the shops?",
]
