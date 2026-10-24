"""English FRESH set in the English Singapore and Malaysia actually read, Singlish and Manglish included: the scams that arrive there (SingPost and Ninja Van fees, DBS and
Maybank and CPF and LHDN phishing, a "new number" mum or bro, a fake police inspector, like-and-earn jobs with a deposit, a Deepavali draw with a fee, Grab asking for an OTP, a
VIP crypto group, TNB, a work-pass fine paid in gift cards, a room-rental deposit, a SIM KYC call, a romance investment, an .apk "summons", an iPhone giveaway) and the ordinary
messages beside them (bank OTP and receipts, rides, parcels, clinic, family, telco, boss, MRT, aircon servicing, Shopee, LTA, school fees, CPF, an anti-scam advisory, FairPrice,
a friend, SP, Lazada, Pos Malaysia). Authored, not captured: a development signal, not a benchmark."""

SCAMS = [
    ("singpost-fee", "[SingPost] Your parcel could not be delivered due to incomplete address. Pay $1.80 redelivery fee within 24h: singpost-redeliver.top/pay"),
    ("mum-new-number", "Hi mum this is my new number, phone spoil already. Can help me transfer $1,800 to this account? Pls dont tell dad first ah"),
    ("fake-inspector", "ScamShield alert: Your number is linked to illegal activity. Call Inspector Lim at 6789 1234 now to avoid arrest. Do not tell anyone."),
    ("dbs-login", "DBS: Unusual login detected on your account. Verify now at dbs-secure-verify.cc or your account will be locked within 24 hours."),
    ("like-job", "Part-time job! Like YouTube videos, earn $150 per day, no experience needed. WhatsApp +65 9123 4567 to start. $50 deposit to activate."),
    ("deepavali-draw", "Congrats! You won $20,000 in the Deepavali lucky draw. Pay $250 processing fee first to claim. WhatsApp 8123 9876."),
    ("cpf-refund", "CPF Board: you have an unclaimed refund of $1,240. Login with SingPass at cpf-refund-claim.com within 48 hours."),
    ("maybank-restricted", "Maybank2u: Your account has been restricted. Update details at maybank-secure-update.xyz or access will be suspended."),
    ("bro-paynow", "Bro, urgent. My card spoil, can you PayNow me $800? I pay you back tomorrow. Cannot call now, in meeting."),
    ("grab-otp", "Hello, this is Grab support. We overcharged your ride. To refund, please send us the OTP you just received."),
    ("vip-crypto", "Join our Telegram VIP group, guaranteed 30% weekly profit from crypto trading. Min $500. Mentor will guide you."),
    ("tnb-cut", "TNB: your electricity bill is overdue. Pay RM 342 before 5pm today or supply will be cut. Pay: tnb-bayar-segera.cc"),
    ("work-pass-fine", "Immigration: your work pass has a violation. Pay the $2,000 fine immediately via gift cards to avoid deportation."),
    ("room-rental", "Hi, I saw your listing for the room. I'm overseas now, can't view. I'll pay deposit first, just send me your bank details and NRIC photo."),
    ("lhdn-refund", "LHDN: You are eligible for tax refund RM 2,350. Submit bank details at lhdn-refund-my.top today."),
    ("shopee-refund", "Shopee: Your order failed. Refund $89.90 – enter card number and CVV at shopee-refund-claim.top"),
    ("sim-kyc", "Dear customer, your SIM will be deactivated tonight. Update KYC by calling 9876 5432 and tell us your IC number."),
    ("oil-rig", "Hello dear, I'm an engineer on an oil rig. I love talking to you. I want to invest with you, send $1,000 and I'll double it."),
    ("apk-summons", "Police report filed against you. Download this app (case_file.apk) to view the summons. Pay the penalty or be arrested."),
    ("iphone-giveaway", "Free iPhone 15 giveaway! Pay only $9.90 shipping to claim: iphone-gift-sg.top. Limited to first 100."),
]

LEGIT = [
    ("dbs-otp", "DBS: Your OTP is 482913. Do not share it with anyone, including DBS staff. Valid for 5 mins."),
    ("posb-spend", "POSB: $45.60 spent at NTUC FairPrice on 12 Oct. Available balance $1,284.30."),
    ("grab-arriving", "Grab: Your driver Suresh is arriving in 3 mins. Plate SGX1234A."),
    ("ninja-van", "Ninja Van: Your parcel will be delivered today between 3pm and 6pm. Please ensure someone is home."),
    ("clinic", "Raffles Clinic: Reminder – appointment with Dr Tan tomorrow 10.30am. Please arrive 15 mins early."),
    ("mum-dinner", "Mum: dinner at 7 tonight, I made curry. Bring your sister along."),
    ("singtel", "Singtel: Your 30GB plan is active until 30 Oct. Check usage on the My Singtel app."),
    ("boss-slides", "Boss, the client presentation is moved to Thursday 2pm. I'll send the slides tonight."),
    ("smrt", "SMRT: East-West Line delayed by about 10 min due to a signal fault. Free bus services available."),
    ("aircon", "Hi Mr Lee, your aircon servicing is confirmed for Saturday 10am. Our technician Ah Kow will call before arriving."),
    ("shopee-shipped", "Shopee: Your order has been shipped and should arrive in 3-5 working days. Track it in the app."),
    ("lta-bus", "LTA: Bus service 190 will be diverted this weekend. Check SG BusLeh for details."),
    ("school-fees", "Reminder: school fees of $40 due by the 10th. Please pay at the general office. Thank you."),
    ("cpf-credit", "CPF Board: Your October contribution has been credited. View your balance on the CPF app."),
    ("anti-scam", "Anti-scam advisory: Don't click on links in SMS. If in doubt, call the ScamShield helpline at 1799."),
    ("fairprice", "NTUC FairPrice: 20% off fresh vegetables this weekend with your Link card."),
    ("lunch", "Bro, lunch tomorrow at 12.30 at the usual place? Let me know."),
    ("sp-bill", "SP Services: Your October bill of $86.40 is ready. Pay by 12 Nov via the SP app or GIRO."),
    ("lazada", "Lazada: 11.11 sale starts at midnight. Check your vouchers in the app. Terms apply."),
    ("pos-my", "Pos Malaysia: Your parcel has arrived at the post office. Please collect with your original IC. Opening hours 9am-5pm."),
]
