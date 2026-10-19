"""Labeled messages for the Check gate (PLAN §8 Phase 1). expect = acceptable verdicts."""
from core.domain.schemas import Verdict as V

SCAMS = [
    ("DHL: Your parcel is held. Pay a $1.99 fee within 24 hours: dhl-fee-pay.xyz/track", {V.SCAM, V.LIKELY_SCAM}, "urgency-pressure"),
    ("Hi grandma, I'm in trouble. Buy 4 gift cards and send me the numbers. Don't tell Mom.", {V.SCAM}, "irreversible-payment"),
    ("Security alert: we texted you a 6-digit code. Reply with that code to cancel the sign-in.", {V.SCAM, V.LIKELY_SCAM}, "otp-credential-phish"),
    ("Microsoft Support: virus found. Install AnyDesk so our technician can fix it.", {V.SCAM}, "remote-access-request"),
    # multilingual (Spanish): needs the LLM to be tagged reliably; offline we only require non-safe.
    ("Su paquete está retenido. Pague 2 dólares en las próximas 24 horas: correos-pago.top/envio", {V.SCAM, V.LIKELY_SCAM, V.UNSURE}, None),
]
BENIGN_BUT_MONEY = [
    "Hi, it's Sam from the club. Can you send me the $20 for the jersey? I'll bring it Saturday.",
    "Your verification code is 482913. Don't share it with anyone.",
]
VICTIM = ["I already paid them with gift cards and now I think I've been scammed"]
