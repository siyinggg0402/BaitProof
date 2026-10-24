"""Malay and Indonesian scam knowledge: pattern strings only (case-insensitive, with word boundaries). The two languages share most of the vocabulary
that scams use, so one pack serves both. These patterns run only when the message is detected as 'ms' (see core.lang.text.Dual).
Each block mirrors an English one in core/pipelines/check and a Chinese one in zh.py."""
from __future__ import annotations


def J(*alts: str) -> str:
    return "|".join(alts)


S = r"[^.!?\n]"  # inside one sentence

_WITHIN = r"dalam(?: masa)? \d+ ?(?:jam|minit|hari)"
_DO = r"(?:kemaskini|sahkan|mengesahkan|hubungi|menghubungi|bayar|membayar|klik|mengklik|balas|tuntut|menuntut|daftar|mendaftar|verifikasi|selesaikan|transfer|mentransfer|pindahkan|memindahkan|kembali|atau)"
DEADLINE = J(rf"\b{_WITHIN}{S}{{0,40}}\b{_DO}\w*", rf"\b(?:sila|harap|wajib|mesti|harus|segera){S}{{0,20}}\b{_WITHIN}", r"\bsegera\b", r"\bsekarang juga\b", r"\bhari ini juga\b", r"\bsecepatnya\b",
             r"\b(?:amaran|peluang|peringatan) terakhir\b", r"\bsebelum (?:pukul|jam) \d",
             rf"\batau \w+{S}{{0,30}}\b(?:akan )?(?:di|dib)?(?:sekat|bekukan|tutup|gantung|blokir|nonaktifkan|kembalikan|batalkan|hapus)\w*", r"\bakan (?:di|dib)(?:sekat|bekukan|tutup|gantung|blokir|nonaktifkan|kembalikan|batalkan|hapus)\w*")
STRONG_DEADLINE = J(rf"\b{_WITHIN}{S}{{0,40}}\b{_DO}\w*", r"\bsegera (?:kemaskini|sahkan|hubungi|bayar|klik|verifikasi|transfer)", r"\bsekarang juga\b", r"\b(?:amaran|peluang|peringatan) terakhir\b",
                    rf"\batau \w+{S}{{0,30}}\b(?:akan )?(?:di|dib)?(?:sekat|bekukan|tutup|gantung|blokir|nonaktifkan|kembalikan|batalkan)\w*", r"\bwaran tangkap\b")
THREAT = J(r"\b(?:blacklist|daftar hitam)\b", r"\bdiblokir stnk\b|\bstnk (?:diblokir|diblokir)\b", r"\bakan (?:dibatasi|dicabut|diputus|dihapus|dikunci|dihapuskan)\b", r"\b(?:meteran|aliran listrik|listrik|sambungan) (?:dicabut|diputus|diputuskan)\b", r"\bjika tidak (?:dibayar|dilunasi)\b",rf"\b(?:laporkan|dilaporkan|melaporkan|lapor|laporkan){S}{{0,15}}\b(?:ke |kepada )?(?:polisi|polis|pihak berwajib)\b", r"\bwaran tangkap\b", r"\bditangkap\b", r"\btindakan (?:mahkamah|undang-undang|hukum)\b", r"\b(?:di)?bekukan\b", r"\bdisekat\b", r"\bdigantung\b", r"\bdiblokir\b", r"\bdinonaktifkan\b",
           r"\bpencucian uang\b", r"\bpengubahan wang haram\b", r"\bdidenda\b", r"\bdisita\b", r"\bkasus (?:pencucian|hukum|pidana)\b", r"\bterindikasi\b", r"\bpembatalan lesen\b", r"\bsiasatan rasuah\b")
SECRECY = J(r"\bjangan (?:bagitahu|beritahu|bilang|cakap|beritau|kasih tau|kasih tahu)\b", r"\btak (?:boleh|perlu) (?:bagitahu|beritahu)\b", r"\b(?:rahsiakan|jaga rahsia|kekalkan rahsia)\b",
            r"\bjangan (?:telefon|hubungi) (?:sesiapa|orang lain)\b")
EMOTIONAL = J(r"\bkritis\b", r"\bbiaya (?:operasi|rumah sakit|pengobatan|berobat)\b", r"\bmendesak\b", r"\bkecemasan\b", r"\bkemalangan\b", r"\bkecelakaan\b", r"\bdarurat\b", r"\bditahan polis\b", r"\btolong (?:saya|aku|sangat)\b")
CONSEQUENCE = rf"\b(?:atau|jika tidak|kalau tidak|kalau enggak|jika tidak maka){S}{{0,40}}\b(?:akan|bakal)\b"

NEGATION = J(r"\b(?:jangan|tidak akan|tak akan|tidak pernah|bukan)\b[^.!?]{0,20}$", r"\b(?:telah|sudah|dah|baru)\s+(?:\w+\s+)?$")
_CODE_WORDS = r"(?:kod|kode|otp|tac|pin|sandi|kata laluan|kata sandi|password|kunci|data|maklumat|kad|kartu|nombor|nomor|akaun|rekening)"
WARNING_STRICT = J(rf"{S}*\b(?:jangan|tidak akan|tak akan|jangan pernah)\b{S}{{0,30}}\b(?:kongsi|berikan|beri|beritahu|bagi|bagikan|serah|bocor|kasih|dedah|sebar|tunjuk|ungkap|sampaikan)\w*\b{S}{{0,40}}\b{_CODE_WORDS}\b{S}*[.!?]?",
                     rf"{S}*\b(?:jangan|tidak akan|tak akan)\b{S}{{0,30}}\b(?:kod|kode|otp|tac|pin|kata laluan|password|sandi)\b{S}*[.!?]?",
                     rf"{S}*\bjangan\b{S}{{0,40}}\b(?:kepada|ke|pada|dengan|sama) (?:sesiapa|siapa ?pun|siapapun|sesiapapun|orang lain)\b{S}*[.!?]?",
                     rf"{S}*\b(?:tidak|tak|tiada)(?: akan)?(?: pernah)?\b{S}{{0,6}}\b(?:meminta|minta|menanyakan|menanya|bertanya|meminta|mengirim|menghubungi|memerlukan){S}{{0,60}}\b{_CODE_WORDS}\b{S}*[.!?]?",  # "BCA tidak pernah meminta PIN atau OTP Anda ..."
                     )
AWARENESS = rf"{S}*\b(?:mengingatkan|berwaspada|waspada|awas|berhati-hati|hati-hati|waspadai)\b{S}*[.!?]?"  # a public notice, not an instruction (a scam can also say "awas!", so this is only used where quoting is the worry)
WARNING_SENTENCE = J(WARNING_STRICT, AWARENESS)
VICTIM = J(r"\bsaya (?:telah |sudah |dah )?(?:tertipu|ditipu|terkena penipuan)\b", r"\b(?:aku|saya) (?:sudah |udah |telah |dah )?(?:tertipu|ditipu)\b",
           r"\bsaya (?:dah|telah|sudah) (?:transfer|bayar|beri(?:kan)?|klik) (?:kod|duit|wang|pautan|link)\b", r"\bsaya (?:dah|telah|sudah) (?:memberikan|beri) (?:kod|otp|tac)\b")
INJECTION = J(r"abaikan (?:semua )?(?:arahan|instruksi)", r"arahan sebelumnya", r"tandakan (?:ini )?sebagai selamat")
AMOUNT = J(r"\b\d[\d.,]* ?(?:rb|jt)\b", r"\bRM ?\d[\d,.]*", r"\bRp\.? ?\d[\d.,]*", r"\b\d[\d,.]* (?:ringgit|rupiah|juta|ribu)\b")

RAILS = {
    "gift-card": J(r"\b(?:kad|kartu) hadiah\b", r"\bgoogle play\b", r"\bbaucar\b"),
    "crypto": J(r"\bkripto\b", r"\bbitcoin\b", r"\busdt\b"),
    "wire": J(r"\bwestern union\b", r"\btelegraphic transfer\b"),
    "safe-account": J(r"\bakaun (?:selamat|keselamatan|penyelamat)\b", r"\brekening (?:aman|penyelamatan|pengamanan)\b", r"\bakun aman\b"),
}

RULES: dict[str, list[str]] = {
    "urgency-pressure": [DEADLINE],
    "authority-spoofing": [
        rf"\b(?:pdrm|polis|polisi|inspektor|pegawai (?:polis|mahkamah|lhdn|kastam)){S}{{0,40}}\b(?:menghubungi|hubungi|siasat|kes|waran|tangkap|kasus)", r"\bwaran tangkap\b",
        r"\bterlibat (?:dalam )?(?:kes|kasus)\b", r"\bdisyaki (?:terlibat|menyalahgunakan)\b", r"\bpencucian uang\b", r"\bpengubahan wang haram\b", r"\b(?:akaun selamat|rekening aman|rekening penyelamatan|rekening pengamanan)\b",
        rf"\b(?:sprm|kastam|jpj|lhdn){S}{{0,50}}\b(?:siasatan|rasuah|tersenarai|barang larangan|saman)\b", r"\bterindikasi digunakan\b"],
    "otp-credential-phish": [
        rf"\b(?:kod|kode)\s*(?:otp|tac)\b{S}{{0,40}}\b(?:beritahu|berikan|beri|bagi|kongsi|sebut|serah)\w*", rf"\b(?:beritahu|berikan|beri|sebut|serahkan)\w*\b{S}{{0,20}}\b(?:kod|kode)\b{S}{{0,25}}\b(?:kepada|ke|pada) (?:pegawai|petugas|kami|agen|staf)\b",
        rf"\b(?:berikan|beri|hantar|kirim|sahkan){S}{{0,20}}\b(?:kata laluan|password|nombor kad|kartu kredit)\b"],
    "too-good-to-be-true": [
        rf"\btahniah\b{S}{{0,60}}\b(?:menang|memenangi|terpilih|hadiah)\b", r"\banda (?:telah )?(?:menang|memenangi|terpilih)\b", r"\bselamat!? anda memenangkan\b", r"\bmemenangkan hadiah\b",
        r"\bcabutan bertuah\b", rf"\b(?:memenangkan|menang|pemenang){S}{{0,30}}\b(?:undian|hadiah|rp ?[\d.]+|rm ?[\d,]+)", r"\bundian (?:poin|berhadiah|bertuah)\b", r"\bbonus (?:saldo|uang|dana)\b",
        rf"\b(?:klik|buka|tekan){S}{{0,30}}\b(?:mencairkan|cairkan|pencairan|mengklaim|klaim|menuntut|tuntut|menukar)\b", rf"\b(?:bantuan sosial|bansos|subsidi (?:listrik|bbm)){S}{{0,40}}\b(?:rp|rm|juta|ribu)\b", r"\bpasti untung\b", r"\bdijamin untung\b", r"\bmodal selamat\b", r"\btanpa risiko\b", r"\b(?:tiada|tanpa) pengalaman\b",
        rf"\bkomisen{S}{{0,20}}\b(?:sehari|per hari)\b", rf"\bgaji{S}{{0,20}}\b(?:per hari|sehari)\b"],
    "emotional-manipulation": [
        rf"\b(?:tentara|prajurit|militer|askar){S}{{0,40}}\b(?:pbb|suriah|afghanistan|irak|luar negeri|misi)\b", r"\bmau kirim (?:paket|hadiah|uang)\b",
        r"\b(?:nombor|nomor|no\.?) baru(?:ku|nya)?\b", r"\btelefon rosak\b", r"\bhp (?:lagi |saya )?rusak\b",
        rf"\bjangan (?:beritahu|bilang|bagitahu){S}{{0,15}}\b(?:abah|ayah|mak|ibu|papa|mama|bapak|suami|isteri)\b", r"\bkemalangan\b", r"\bditahan polis\b"],
    "remote-access-request": [
        rf"\b(?:muat turun|download|pasang|install|unduh){S}{{0,20}}\b(?:anydesk|teamviewer|apk)\b", r"\b(?:capaian|akses) jauh\b", r"\b[\w-]+\.apk\b"],
    "advance-fee": [
        r"\b(?:yuran|biaya|cukai|bayaran|caj) (?:proses|pemprosesan|administrasi|admin|kastam|pelepasan|pengurusan|penghantaran semula)\b", r"\bbiaya (?:insurans|asuransi)\b",
        r"\bpengurusan dokumen\b", r"\bsetor modal\b", r"\b(?:biaya|ongkos|ongkir|bayaran) (?:pengiriman|kirim|pengangkutan|pelepasan|penghantaran)\b", r"\b(?:biaya|uang|bayaran|yuran) (?:pendaftaran|seragam|pelatihan|registrasi|aktivasi|administrasi|pakaian)\b", rf"\b(?:rekening|akaun) (?:pribadi|peribadi){S}{{0,40}}\b(?:tidak perlu laporan|kirim bukti|hantar bukti)\b",
        rf"\bbayar (?:yuran|biaya|cukai){S}{{0,40}}\b(?:dahulu|dulu|terlebih dahulu|untuk (?:menuntut|dilepaskan|melepaskan))\b", rf"\bcukup bayar\b{S}{{0,40}}\b(?:asuransi|insurans|biaya|yuran)\b",
        r"\btanpa (?:jaminan|cagaran)\b", r"\bdeposit (?:awal|rm|rp)\b", r"\bbayar dulu\b", rf"\b(?:bayar|transfer|setor|kirim){S}{{0,35}}\b(?:dulu|dahulu|terlebih dahulu)\b", r"\b(?:dp|uang muka) (?:rp|rm)? ?[\d.]+"],
    "impersonation-official": [
        rf"\b(?:lhdn|pdrm|kastam|bea cukai|pos laju|poslaju|j&t|dhl|bank negara|sprm|jpj|imigresen|polri|korlantas|e-?tilang){S}{{0,50}}\b(?:tunggakan|tertunggak|cukai|saman|tertahan|ditahan|disekat|dibekukan|tidak dapat dihantar|alamat tidak lengkap|bayar|denda|dikembalikan)\b",
        r"\bpaket anda tertahan\b", r"\btunggakan cukai\b"],
    "investment-crypto": [
        rf"\b(?:pelaburan|investasi){S}{{0,40}}\b(?:untung|pulangan|keuntungan|dijamin|pasti|modal selamat|dana aman)\b", r"\b(?:untung|pulangan|keuntungan) \d+ ?%", r"\b\d+ ?% (?:sebulan|per bulan|setiap bulan)\b",
        r"\bkripto\b", r"\b(?:grup|kumpulan) vip\b", r"\bejen kami\b"],
    "job-task-scam": [
        rf"\blowongan(?: kerja)?{S}{{0,30}}\b(?:online|tanpa tes|tanpa pengalaman|langsung kerja)\b", r"\bkerja sambilan\b", r"\bkerja (?:dari rumah|online|atas talian)\b", r"\bsehari rm ?\d", r"\bpendapatan sampingan\b", r"\blike dan subscribe\b",
        rf"\btugasan\b{S}{{0,40}}\b(?:komisen|upah|bayar)\b", r"\blowongan kerja online\b", r"\bgaji rp ?[\d.]+ (?:ribu )?per hari\b", r"\bsertai kumpulan (?:telegram|whatsapp)\b",
        rf"\bdeposit\b{S}{{0,20}}\b(?:untuk mula|awal|aktifkan)\b", r"\b(?:menyukai|menyukai|like|suka) video\b", rf"\b(?:dapatkan|raih){S}{{0,20}}\brp ?[\d.]+ ?(?:ribu|juta)? per hari\b",
        rf"\b(?:deposit|biaya|bayar|transfer|setor){S}{{0,30}}\baktivasi\b|\baktivasi\b{S}{{0,25}}\b(?:deposit|biaya|akun tugas|akun kerja)\b"],
}

ASK = {
    "pay": J(rf"\b(?:isi|isiin|isikan|beliin|belikan|kirimin|kirim){S}{{0,15}}\b(?:pulsa|token listrik|voucher|saldo)\b", rf"\b(?:bayar|membayar|pindahkan|memindahkan|transfer|mentransfer|hantar wang|top ?up|deposit|salurkan|kirim|mengirim|setor|lunaskan|beli){S}{{0,40}}(?:\bRM|\bRp|\$|\d+ ?(?:ringgit|rupiah)|\byuran\b|\bcukai\b|\bbayaran\b|\bbiaya\b|\bfee\b|\bcaj\b|\bkad hadiah\b|\bkartu hadiah\b|\bbitcoin\b|\bkripto\b|\bwang\b|\bduit\b|\bakaun\b|\brekening\b|\bsaldo\b|\bdana\b|\bsekarang\b)",
             r"\bsila (?:bayar|buat bayaran|transfer|pindahkan)\b", r"\bbayar (?:dahulu|dulu|terlebih dahulu|segera)\b", r"\bperlu (?:bayar|transfer|membayar)\b", r"\bcukup bayar\b"),
    "share_code": J(rf"\b(?:beritahu|bagi|beri|berikan|kongsi|hantar|balas|sebut|bacakan|serahkan|kasih|kirim|sampaikan|sebutkan){S}{{0,25}}\b(?:kod|kode|otp|tac|pin|kata laluan|password|sandi)\b",
                    rf"\b(?:kod|kode) (?:otp|tac){S}{{0,25}}\b(?:kepada|ke|pada) (?:pegawai|petugas|kami|saya|staf|agen)\b"),
    "share_credentials": J(rf"\b(?:berikan|beri|memberi|memberikan|hantar|menghantar|sahkan|mengesahkan|masukkan|isi|kemaskini|sediakan|serahkan|menyerahkan|kirim|mengirim|siapkan|verifikasi){S}{{0,35}}\b(?:kata laluan|password|pin|nombor kad|nomor kartu|kad kredit|kad debit|nombor akaun|butiran (?:bank|akaun|peribadi|kad)|maklumat (?:peribadi|bank|akaun|kad)|data (?:pribadi|diri)|nomor (?:kartu|rekening)|ic|nric|mykad|ktp|nik|npwp|selfie|foto ktp|kartu keluarga|kartu kredit)\b",
                           r"\bsahkan (?:butiran|maklumat|akaun) anda\b", r"\bverifikasi data\b"),
    "install": J(rf"\b(?:muat turun|download|pasang|install|unduh){S}{{0,20}}\b(?:aplikasi|apk|app|perisian|anydesk|teamviewer)\b", r"\b(?:capaian|akses) jauh\b", r"\b[\w-]+\.apk\b"),
    "click": J(rf"\b(?:klik|tekan|ketik|buka){S}{{0,20}}\b(?:pautan|link|laman|tautan|url)\b", r"\bklik (?:di sini|disini|link)\b"),
    "call": J(r"\b(?:hubungi|telefon|panggil|menghubungi|telepon)\b"),
    "reply": J(r"\bbalas\b"),
}
RELATIONS = r"\b(?:mak|ibu|emak|ayah|abah|abang|kakak|adik|nenek|atuk|datuk|mamah|mama|papa|bapak|anak|sayang|mah|ma|pa|bunda|ibunda|ayahanda)\b"
AUTHORITY = r"\b(?:camat|lurah|kepala desa|kades|bupati|walikota|gubernur|direktur(?: utama)?|bos|atasan|pimpinan|ceo|manajer|manager|pdrm|polis|polisi|inspektor|mahkamah|pengadilan|lhdn|kastam|bea cukai|sprm|bank negara|bnm|imigresen|jpj|kwsp|perkeso|kejaksaan|kepolisian|bareskrim|ojk|ditjen pajak)\b"
ORGANISATION = (r"\b(?:maybank|cimb|public bank|rhb|bank islam|bsn|affin|hong leong|bca|bri|bni|mandiri|ocbc|dbs|uob|pos laju|poslaju|j&t|jnt|shopee|lazada|tokopedia|grab|gojek|touch ?'?n ?go|tng|tnb|petronas|telekom|unifi|maxis|celcom|digi|telkomsel|indosat)\b"
                r"|\b(?:pegawai bank|khidmat pelanggan|cs kami|pihak bank)\b")
OPENER = J(r"\bsalah kirim\b", r"\b(?:kenal|kenalan) dengan (?:saya|aku)\b", r"\bboleh (?:berteman|berkenalan|kenal)\b", r"\b(?:nombor|nomor|no\.?|number) baru(?:ku|nya)?\b", r"\btelefon rosak\b", r"\bhp (?:lagi |saya )?rusak\b", r"\bsalah (?:nombor|nomor)\b",
           rf"\b(?:tambah|add|hubungi|pm) (?:saya|kami|aku|admin|ejen){S}{{0,15}}\b(?:whatsapp|telegram|wechat)\b", rf"\bhubungi (?:kami|admin|ejen){S}{{0,25}}\b(?:whatsapp|telegram)\b",
           r"\bsertai (?:kumpulan|group|grup)\b", r"\bgabung (?:grup|group)\b", r"\bsaya (?:lihat|nampak) (?:profil|iklan)\b")
ALARM = r"\b(?:disekat|dibekukan|diblokir|digantung|dikunci|dibatasi|dicabut|belum terverifikasi|tidak terverifikasi|mencurigakan|tidak sah|dinonaktifkan|ditutup|tunggakan)\b"
ACTION = r"\b(?:sahkan|verifikasi|kemaskini|hubungi|klik|log masuk|login|aktifkan semula|bayar)\b"
NEW_NUMBER = r"\b(?:nombor|nomor|no\.?) baru(?:ku|nya)?\b|\btelefon rosak\b|\bhp (?:lagi |saya )?rusak\b"
CALL_POSSIBLE = r"\b(?:hubungi|telefon|telepon|panggil)\b|\d{3}[\s.-]?\d{3,}"

SCENARIO_SIGNS = {
    "parcel-fee": [
        r"\b(?:bungkusan|pakej|parcel|paket|penghantaran|pengiriman|kurier|kurir|bea cukai|kastam|pos laju|poslaju|j&t|jnt)\b",
        r"\b(?:yuran|bayaran|biaya|cukai|bayar)\b|\brp ?\d|\brm ?\d",
        r"\b(?:tertahan|tidak dapat dihantar|alamat tidak lengkap|dikembalikan|ditahan|gagal dihantar|dikenakan|belum dibayar)\b",
        r"\b(?:kemaskini|sahkan|klik|pautan|tautan)\b|https?://"],
    "bank-security": [
        r"\b(?:akaun|rekening|kad|bank|maybank|cimb|bca|bri|mandiri|bni|rhb|public bank)\b",
        r"\b(?:disekat|dibekukan|diblokir|digantung|dikunci|mencurigakan|tidak sah|ditutup)\b",
        r"\b(?:sahkan|verifikasi|kemaskini|hubungi|klik|log masuk|login|aktifkan semula)\b",
        r"https?://|\bpautan\b|\bkod\b|\bhubungi\b|\bcs\b"],
    "family-emergency": [
        r"\b(?:mak|ibu|emak|ayah|abah|abang|kakak|adik|nenek|atuk|mamah|mama|papa|bapak|anak|sayang)\b",
        r"\b(?:nombor baru|nomor baru|telefon rosak|hp (?:lagi )?rusak|kemalangan|hospital|ditahan|polis|mengalami masalah)\b",
        r"\b(?:transfer|pindahkan|hantar wang|bantu bayar|minta duit|pinjam)\b|\brm ?\d|\brp ?\d",
        r"\b(?:jangan (?:beritahu|bilang|bagitahu)|sekarang|segera|cepat|urgent|darurat)\b"],
    "prize-lottery": [
        r"\b(?:tahniah|selamat|menang|memenangi|memenangkan|hadiah|undian|cabutan|terpilih)\b",
        r"\b(?:tuntut|menuntut|claim|hubungi|ambil|terima)\b",
        r"\b(?:yuran|biaya|bayar|transfer|cukai|admin|klik)\b|https?://|\brm ?\d|\brp ?\d"],
    "tax-government": [
        r"\b(?:pdrm|polis|polisi|lhdn|kastam|bea cukai|sprm|jpj|kwsp|perkeso|imigresen|mahkamah|pengadilan|bank negara|pajak|kejaksaan|bareskrim)\b",
        r"\b(?:tunggakan|tertunggak|saman|waran|kes|kasus|pencucian uang|pengubahan wang haram|disyaki|terlibat|denda|cukai|rasuah|siasatan|kelebihan bayar|restitusi|pengembalian (?:pajak|dana))\b",
        r"\b(?:bayar|hubungi|segera|transfer|akaun selamat|rekening aman|jangan beritahu|siasat|diperiksa|klik|pautan|sahkan|memberi)\b|https?://"],
    "job-task": [
        r"\b(?:kerja|lowongan|komisen|gaji|tugasan|pendapatan|sambilan|upah)\b",
        r"\b(?:sehari|per hari|tiada pengalaman|tanpa pengalaman|dari rumah|online|atas talian|like|subscribe)\b",
        r"\b(?:deposit|telegram|whatsapp|sertai|daftar|top ?up|modal)\b"],
    "investment": [
        r"\b(?:pelaburan|investasi|saham|kripto|forex|emas|trading)\b",
        r"\b(?:untung|pulangan|dijamin|pasti|modal selamat|dana aman)\b|\d+ ?%",
        r"\b(?:daftar|sertai|gabung|hubungi|ejen|grup|kumpulan|vip|deposit)\b"],
    "account-verification": [
        r"\b(?:akaun|akun|whatsapp|facebook|email|emel|kata laluan|password)\b",
        r"\b(?:sahkan|verifikasi|kemaskini|klik|log masuk|login)\b",
        r"\b(?:dinonaktifkan|disekat|digantung|ditutup|mencurigakan)\b|\bdalam \d+ jam\b",
        r"https?://|\bpautan\b|\bkod\b"],
    "utility-bill": [
        r"\b(?:listrik|pln|pdam|air|gas|tagihan|bil|elektrik)\b",
        r"\b(?:menunggak|tunggakan|tertunggak|diputus|dicabut|diputuskan|dipotong|pemutusan|terputus)\b",
        r"\b(?:bayar|hubungi|segera|hari ini|sekarang|klik|tautan|link)\b|https?://"],
    "ticket-prepay": [
        r"\b(?:tiket|karcis|konser|tiket pesawat)\b",
        r"\b(?:promo|murah|harga spesial|diskon|hanya rp|terbatas|sisa)\b",
        rf"\b(?:transfer|setor){S}{{0,40}}\b(?:rekening|dana|ovo|gopay)\b|\b(?:dp|uang muka)\b"],
    "romance": [
        r"\b(?:sayang|cinta|tentara|prajurit|janda|duda)\b",
        r"\b(?:luar negeri|suriah|pbb|misi|ditugaskan|kapal minyak|aplikasi kencan|online)\b",
        r"\b(?:kirim|bayar|biaya|paket|transfer|tiket|bea cukai|investasi)\b"],
    "charity-appeal": [
        r"\b(?:donasi|sumbangan|derma|bantuan korban|korban banjir|korban bencana)\b",
        r"\b(?:rekening|akaun) (?:pribadi|peribadi)\b|\ba\.?n\.?\b|\b(?:tidak perlu laporan|kirim bukti|hantar bukti)\b",
        r"\b(?:wa|whatsapp|link|tautan|transfer|salurkan|kirim)\b"],
    "inheritance-advance-fee": [
        r"\b(?:pinjaman|pinjam|kredit|pembiayaan|dana)\b",
        r"\b(?:disetujui|diluluskan|lulus|tanpa jaminan|tanpa cagaran|pasti lulus)\b",
        r"\b(?:yuran|biaya|asuransi|insurans|bayar|deposit|admin)\b"],
}

PURPOSE_CUES = {
    "appointment-booking": r"\b(?:temu janji|janji temu|temujanji|tempahan|jadwal|jadual|konsultasi|reservasi|pengesahan)\b",
    "delivery-update": r"\b(?:bungkusan|pakej|paket|penghantaran|pengiriman|dihantar|dikirim|tiba|sampai|kurier|kurir|pesanan)\b",
    "transaction-alert": r"\b(?:pembayaran|bayaran|transaksi|baki|saldo|dibayar|berhasil|berjaya|mutasi|penyata)\b",
    "one-time-code": r"\b(?:kod|kode)\s*(?:otp|tac|pengesahan)?[^.!?\n]{0,30}\b\d{4,8}\b|\botp\b[^.!?\n]{0,30}\b\d{4,8}\b",
    "account-notice": r"\b(?:akaun|akun|kata laluan|log masuk|langganan)\b",
    "work-logistics": r"\b(?:mesyuarat|rapat|kelas|sekolah|pejabat|kantor|projek|pasukan)\b",
    "invoice-or-bill": r"\b(?:bil|tagihan|invois|faktur|sewa|yuran|tunggakan|jumlah)\b",
    "marketing-offer": r"\b(?:diskaun|promosi|tawaran|promo|potongan|jualan|baucar)\b",
    "request-install-access": r"\b(?:muat turun|pasang|install|unduh|akses jauh|capaian jauh)\b",
    "claim-prize-reward": r"\b(?:menang|memenangi|hadiah|tuntut|tahniah|undian|bonus|bayaran balik)\b",
    "offer-job-or-investment": r"\b(?:kerja sambilan|lowongan|komisen|gaji|pelaburan|investasi|pinjaman|saham|kripto|tugasan)\b",
    "urgent-account-warning": r"\b(?:disekat|dibekukan|diblokir|digantung|mencurigakan|segera|tunggakan|waran|dinonaktifkan)\b",
    "emotional-plea": r"\b(?:tolong|kecemasan|kemalangan|darurat|ditahan|jangan beritahu|jangan bilang)\b",
}
STATUS = r"\b(?:telah|sudah|akan|sedang)\b[^.!?]{0,20}\b(?:dihantar|dikirim|tiba|sampai|diterima|dalam perjalanan|tersedia)\b|\bkode pengambilan\b|\btitik pengambilan\b|\bkode (?:ambil|pengambilan)\b"
NEGATIVE = r"\b(?:yuran|bayar|bayaran|biaya|klik|pautan|link|balas|hubungi|telefon|segera|sekarang|kemaskini|sahkan|verifikasi|menang|hadiah|tuntut|tertahan|gagal|dikembalikan|disekat)\b"
PREMIUM = J(rf"\b(?:txt|text|sms|ketik|ketikkan|kirim|kirimkan|hantar|balas|reg|daftar){S}{{0,70}}\b(?:ke|kepada|to|2|ke nombor|ke nomor)\s*\d{{4,6}}\b", r"\b\d{2,}\s?(?:sen|p|perak|rupiah)\s?(?:per|/|setiap)\s?(?:sms|mesej|pesan|menit|minit|minggu)\b",
            r"\b(?:rp|rm)\s?\d+(?:[.,]\d+)?\s?(?:/|per|setiap)\s?(?:sms|mesej|pesan|menit|minit|minggu|hari)\b", rf"\b(?:berlangganan|langganan|subscribe){S}{{0,40}}\b(?:pulsa|sms premium)\b")
CODE_REQ = r"\b(?:balas|beritahu|berikan|beri|kongsi|hantar|sebut|masukkan|klik|hubungi)\b"  # not "verifikasi": in "kode verifikasi" it is the noun
APPT = r"\b(?:temu janji|janji temu|jadwal|jadual|konsultasi|tempahan|reservasi)\b"
TIME = r"\b\d{1,2}[:.]\d{2}\b|\b(?:pukul|jam) \d{1,2}\b|\b(?:esok|besok|hari ini|malam ini|isnin|selasa|rabu|khamis|jumaat|sabtu|ahad|senin|kamis|jumat|minggu)\b"
APPT_NEGATIVE = r"\b(?:yuran|deposit|bayar|menang|percuma|segera|klik|pautan)\b"

PRE = {
    "money_rail": r"\b(?:kad hadiah|kartu hadiah|bitcoin|kripto|usdt|western union|akaun selamat|rekening aman|pindahan bank|transfer)\b",
    "remote": r"\b(?:anydesk|teamviewer|muat turun|pasang|akses jauh|capaian jauh)\b",
    "secret_ask": rf"\b(?:beri|berikan|beritahu|kongsi|hantar|sebut|masukkan|sahkan){S}{{0,25}}\b(?:kod|kode|otp|tac|pin|kata laluan|password|nombor kad|nombor akaun|ic|mykad)\b",
    "job": r"\b(?:kerja|lowongan|komisen|gaji|tugasan|sambilan|pendapatan|upah)\b",
    "invest": r"\b(?:pelaburan|investasi|saham|kripto|forex|pulangan|untung|keuntungan|modal|dana)\b|\d+ ?%",
    "fee": r"\b(?:yuran|biaya|cukai|bayar|bayaran|transfer|deposit|insurans|asuransi|admin|denda)\b",
    "authority": r"\b(?:pdrm|polis|polisi|lhdn|kastam|bea cukai|sprm|mahkamah|pengadilan|bank negara|inspektor|pegawai)\b",
    "emotional": r"\b(?:tolong|kecemasan|kemalangan|darurat|ditahan|jangan beritahu|jangan bilang|sayang|percaya)\b",
    "windfall": r"\b(?:menang|memenangi|hadiah|tahniah|undian|cabutan|untung|pulangan|bonus|komisen|gaji|pinjaman|diluluskan|disetujui)\b",
}
