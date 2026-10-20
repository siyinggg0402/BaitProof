"""Held-out set #2: written AFTER set #1 was used for tuning, to measure generalisation.
First-run results are recorded in the README; any rule fixes after that make this a dev set too."""

SCAMS = [
    ("Hi, I'm texting about the overdue toll on your account. Settle $12.40 at once to avoid a late fine: toll-settle-now.top/pay", "toll"),
    ("Dear user, your mailbox storage is full and incoming emails will be deleted. Click to upgrade for free: mail-storage-fix.xyz", "mailbox"),
    ("Mum, I've got a new phone, this is my new number. Can you save it and send me $400 for the deposit on my flat? Need it by 5.", "new-number"),
    ("Hello, we are calling from your internet provider. Your line has been compromised. Please give us remote access so we can secure it.", "remote"),
    ("Your Amazon Prime membership will renew for $349.99 today. To cancel, call 1-855-555-0101 immediately.", "renewal-callback"),
    ("I saw your resume online. We pay $200 a day for simple social media tasks. Reply YES and I will send the details on WhatsApp.", "job"),
    ("Congratulations, you've been pre-approved for a $25,000 loan. No credit check, pay a $199 insurance fee to receive it today.", "loan"),
    ("URGENT: Your Microsoft account has been compromised. Do not shut down your computer. Call support now.", "tech-support"),
    ("Hi love, I'm stuck at the border and they need a $1,500 fine paid in gift cards or they'll detain me. Please hurry, don't call.", "family-gift"),
    ("This is the Social Security Administration. Your number is linked to money laundering. Press 1 to avoid arrest.", "ssa"),
    ("Your bank has sent you a new secure message. Sign in to read it: secure-bankmail-login.com", "bank-lookalike"),
    ("Invest in our new token. Early backers made 12x in a month. Transfer ETH to the address below before the presale closes tonight.", "crypto"),
    ("Hello, I am a US soldier and I trust you. I have a box with $3 million I need you to receive. Please send your address and bank details.", "soldier"),
    ("Your phone bill is overdue. To avoid disconnection, pay immediately with an iTunes gift card.", "bill-gift"),
    ("Dear homeowner, you qualify for a free government solar grant. Pay a $90 admin fee to lock in your approval.", "grant"),
    ("WhatsApp: your account will be deactivated. Send us the 6-digit code you just received to keep it.", "whatsapp-otp"),
    ("Bonjour, votre colis est en attente. Réglez 1,99 € dans les 24 heures: colis-livraison-fr.top", "fr-parcel"),
    ("Hi, I accidentally sent you $900. Please send it back to this account. I'm in hospital and it's an emergency.", "overpayment"),
    ("Final reminder: unpaid parking fine. Pay within 24 hours to avoid a court summons: pay-fine-online.click", "fine"),
    ("Hey, it's your boss. I'm in a meeting and need you to buy 5 gift cards for clients. Send me the codes, don't call.", "boss-gift"),
]

LEGIT = [
    "Your Uber is arriving in 2 minutes. Look for a grey Toyota Corolla.",
    "Hi, it's the school office. Tomorrow is a half day, pickup is at 12:30.",
    "Can you send me the address for Saturday? I'll put it in my phone.",
    "Your order has shipped and should arrive Thursday. Track it in the app you used to order.",
    "Hi Mum, I'm at the shops. Do you need milk or bread?",
    "Your prescription is ready to collect at the pharmacy. Open until 6pm today.",
    "Thanks for coming in today! We'd love your feedback when you have a moment.",
    "Your flight BA245 is on time. Check-in opens 24 hours before departure.",
    "Reminder: council tax payment is due on the 1st. You can pay through your online account as usual.",
    "Lunch on Sunday at ours? Everyone's coming around 1.",
]
