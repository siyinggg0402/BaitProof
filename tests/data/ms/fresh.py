"""Malay and Indonesian FRESH set: written by hand AFTER the Malay/Indonesian rules existed, with different scams and wording from ms/holdout.py
(whose rules were written with those messages in view, so that set is a development set). Authored, not captured. Measured once; see the README."""

SCAMS = [
    ("tng-kyc", "Akaun Touch 'n Go eWallet anda telah digantung. Naik taraf KYC anda di http://tng-kyc-update.top sebelum 6 petang ini."),
    ("kastam-call", "Salam, saya Pegawai Kastam. Ada bungkusan atas nama anda mengandungi barang larangan. Sila hubungi 011-2233 4455, jangan beritahu keluarga."),
    ("loan-ctos", "Dapatkan pinjaman peribadi RM50,000 tanpa semakan CTOS! Lulus dalam 1 jam. Bayar RM800 untuk pengurusan dokumen dahulu."),
    ("steam-friend", "Hai, awak masih ingat saya? Saya Sarah kawan sekolah dulu. Boleh tolong beli kad hadiah Steam RM200? Nanti saya ganti esok."),
    ("gold-invest", "Anda telah dipilih untuk menyertai program pelaburan emas dengan pulangan 25% seminggu. Pasti untung, modal dijamin. WhatsApp kami."),
    ("bri-rescue", "Tuan, rekening Anda di Bank BRI terindikasi digunakan untuk penipuan. Mohon transfer saldo ke rekening penyelamatan untuk pengamanan."),
    ("shopee-refund", "Selamat siang, saya dari Shopee. Pesanan Anda gagal diproses. Mohon kirimkan kode verifikasi yang masuk ke HP Anda untuk pengembalian dana."),
    ("youtube-like", "Dapatkan Rp 300 ribu per hari hanya dengan menyukai video YouTube. Gabung grup Telegram, setor modal Rp 150.000 untuk aktivasi."),
    ("kak-long-accident", "Mama, ini Kak Long. Saya kemalangan, kereta rosak, perlukan RM3,000 untuk bayar tow. Boleh transfer sekarang? Jangan call, saya tak boleh cakap."),
    ("sprm-mykad", "SPRM: Nama anda tersenarai dalam siasatan rasuah. Sahkan identiti anda dengan memberi nombor MyKad dan kata laluan perbankan online."),
    ("dhl-my", "Pakej DHL anda ditahan di pusat pengedaran. Bayar caj penghantaran RM4.90 di http://dhl-my-redeliver.cc untuk penghantaran semula."),
    ("bank-tac", "Kami dari bank anda. Ada transaksi mencurigakan RM5,600 ke luar negara. Untuk batalkan, sebut kod TAC yang baru anda terima."),
    ("lazada-win", "Menang besar! Nombor telefon anda terpilih dalam cabutan Lazada. Klik http://lazada-menang.top untuk tuntut hadiah RM12,000."),
    ("bni-pin", "Akun BNI Anda terblokir. Segera hubungi petugas kami di WA 0813-9876-5432 dan siapkan nomor kartu serta PIN untuk verifikasi."),
    ("jpj-saman", "Anda mempunyai saman trafik tertunggak RM300. Bayar hari ini untuk elak pembatalan lesen: http://jpj-saman.xyz"),
]

LEGIT = [
    ("tac-real", "Kod TAC anda untuk log masuk ialah 774412. Jangan dedahkan kepada sesiapa, termasuk pegawai bank."),
    ("lunch-ms", "Hai, jom lunch kat kedai mamak pukul 1 nanti? Aku belanja."),
    ("jnt-ship", "Pesanan #A2231 anda telah dihantar oleh J&T Express. Jangkaan tiba: 22 Oktober."),
    ("kakak-groceries", "Mak, kakak dah beli barang dapur. Kakak sampai rumah dalam sejam."),
    ("dentist-ms", "Temu janji gigi anda pada 28/10 jam 3.30 petang telah ditempah. Sila datang 10 minit awal."),
    ("shopee-otp-id", "Kode verifikasi Shopee Anda: 3921. Jangan beri kode ini ke siapa pun, termasuk pihak Shopee."),
    ("meeting-id", "Halo, mau konfirmasi rapat besok jam 10 di ruang meeting lantai 3 ya."),
    ("debit-id", "Transaksi kartu debit Rp 85.000 di Alfamart berhasil pada 20/10 pukul 18.45. Saldo dapat dicek di aplikasi."),
    ("insurance-ms", "Peringatan: bayaran insurans kereta anda akan tamat pada 15 November. Anda boleh perbaharui melalui aplikasi syarikat."),
    ("pickup-ms", "Boleh tolong ambil adik dari sekolah petang ni? Saya ada mesyuarat sampai lewat."),
    ("tuition-ms", "Kelas tuisyen Matematik bermula pukul 4 petang hari Sabtu. Sila bawa buku latihan."),
    ("bnm-notice", "Bank Negara Malaysia mengingatkan orang awam agar tidak mudah percaya panggilan yang mendakwa daripada pihak bank atau polis. Jangan kongsi OTP."),
    ("thanks-id", "Mas, makasih ya sudah bantu kemarin. Nanti kita makan bareng."),
    ("pln-bill", "Tagihan listrik Anda bulan Oktober Rp 245.000 jatuh tempo 20 November. Bayar lewat aplikasi PLN Mobile."),
    ("paid-ms", "Saya dah transfer RM300 untuk duit hadiah hari jadi adik, tolong semak ya."),
]
