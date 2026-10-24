"""Indonesian FRESH set: written by hand AFTER the Indonesian rules had been tuned on tests/data/id/dev.py and read through tests/data/id/holdout.py, to check that the
tuning generalises. New scams (BRI card unblock asking for the PIN, a relative stranded without a wallet, a "driver" job with a uniform fee, customs fines, loans with an admin
fee, WhatsApp account recovery codes, a prize quiz with a prize tax, a "guaranteed by OJK" share group, a credit-card blacklist threat, paid "part-time" tasks, an
.apk tax-return app, a village-head handout asking for a KTP photo, Instagram verification, a car accident abroad, an e-tilang lookalike, ad-clicking jobs, a PLN subsidy,
a "suspicious transaction" call-back, a Tokopedia lookalike, a flood donation to a private account) and new ordinary messages (bank OTP and receipts, ride and shop updates,
school, courier, hospital, telco, neighbourhood, official bank and police advice, wallet, campus, flight, electricity, workshop and family chat). Authored, not captured:
a development signal, not a benchmark. The Indonesian texts are ours and have not been reviewed by a native speaker. Read it as little as possible."""

SCAMS = [
    ("bri-pin", "Selamat pagi Bapak/Ibu, kami dari Bank BRI. Kartu Anda terblokir karena PIN salah 3 kali. Untuk membuka blokir, balas pesan ini dengan PIN dan nomor kartu Anda."),
    ("dompet-hilang", "Kak, ini Dina. Aku lagi di luar kota, dompet hilang. Bisa transfer 750rb ke DANA 0813-4455-6677? Besok aku ganti, jangan kasih tau mama ya."),
    ("driver-seragam", "Lowongan driver online Gojek resmi, tanpa tes, langsung kerja. Biaya pendaftaran seragam Rp 250.000. Hubungi 0877-1234-0000."),
    ("bea-cukai-denda", "Pemberitahuan: Paket Anda dari luar negeri tertahan di Bea Cukai Soekarno-Hatta. Bayar denda Rp 890.000 ke rekening 3344-5566-77 agar dikirim."),
    ("pinjaman-agunan", "Dapatkan pinjaman Rp 5 juta tanpa agunan, cair dalam 10 menit. Syarat: bayar biaya admin Rp 150.000 dulu via transfer."),
    ("wa-pemulihan", "WhatsApp Anda terdaftar di perangkat lain. Kirimkan kode 6 digit yang baru masuk ke SMS Anda untuk memulihkan akun."),
    ("kuis-mobil", "Anda terpilih menjadi pemenang kuis Indomaret berhadiah mobil. Konfirmasi data diri dan transfer pajak hadiah Rp 3.000.000."),
    ("saham-syariah", "Investasi saham syariah untung 20% per bulan dijamin OJK. Gabung grup Telegram kami: t.me/cuan_syariah_vip"),
    ("kartu-kredit-blacklist", "Tagihan kartu kredit Anda jatuh tempo hari ini. Bayar sekarang di bit.ly/tagihan-kk atau dikenakan denda dan blacklist BI."),
    ("rekrutmen-shopee", "Halo, saya dari tim rekrutmen Shopee. Kamu lolos seleksi kerja paruh waktu, gaji Rp 500 ribu per hari. Chat WA 0852-9988-7766 untuk tugas pertama."),
    ("apk-spt", "Bapak Ibu, mohon unduh aplikasi e-faktur terbaru di file Update_Pajak_2024.apk untuk lapor SPT."),
    ("pak-camat", "Ini Pak Camat. Warga RT Anda mendapat bantuan sosial Rp 2 juta. Kirim foto KTP dan buku tabungan lewat WA ini untuk pencairan."),
    ("instagram-verif", "Akun Instagram Anda melanggar kebijakan. Verifikasi identitas di meta-verifikasi-id.com dalam 12 jam atau akun dihapus permanen."),
    ("kecelakaan-medan", "Sayang, aku butuh bantuanmu. Aku kecelakaan di Medan, tolong kirim Rp 4 juta ke rekening rumah sakit ini. Jangan telepon dulu, nanti aku jelaskan."),
    ("ganjil-genap", "Kendaraan Anda terekam melanggar ganjil genap. Cek dan bayar tilang di tilang-polri-cek.top agar tidak diblokir STNK-nya."),
    ("klik-iklan", "Mau kerja dari rumah? Cukup klik iklan setiap hari, penghasilan Rp 800 ribu. Deposit awal Rp 200 ribu untuk aktivasi akun. Daftar di WA 0821-5566-4433."),
    ("subsidi-pln", "Pengumuman: Anda berhak atas subsidi listrik Rp 500 ribu dari PLN. Klaim di pln-subsidi-2024.xyz sebelum Jumat."),
    ("transaksi-curiga", "Kami menemukan transaksi mencurigakan Rp 12.500.000 di rekening Anda. Segera hubungi petugas kami di 0811-2233-4455 dan jangan matikan telepon."),
    ("tokopedia-palsu", "Barang Anda di Tokopedia belum dibayar. Segera selesaikan pembayaran lewat link berikut agar pesanan tidak dibatalkan: toko-pedia-bayar.xyz/inv"),
    ("donasi-banjir", "Bantuan korban banjir. Salurkan donasi ke rekening pribadi 1122-3344-55 a.n. Ahmad. Kirim bukti transfer ke WA ini, tidak perlu laporan."),
]

LEGIT = [
    ("mandiri-otp", "Mandiri: Kode OTP Anda 8421. Berlaku 3 menit. Rahasiakan kode ini, jangan berikan kepada siapa pun termasuk petugas bank."),
    ("bri-transfer", "BRI: Transaksi transfer Rp 500.000 ke Siti Aminah berhasil. Info lebih lanjut hubungi 14017 atau BRImo."),
    ("grab-jemput", "Grab: Driver Anda tiba dalam 2 menit. Mohon siap di titik jemput. Terima kasih."),
    ("shopee-penjual", "Shopee: Pesanan #2406 sudah diterima pembeli. Dana akan dicairkan ke saldo penjual dalam 3 hari kerja."),
    ("osis", "Kak Rani, rapat OSIS dipindah ke Rabu jam 15.30 di ruang musik ya. Tolong kabari teman-teman."),
    ("jne-resi", "Pak, sertifikat barang sudah saya kirim lewat JNE, resi JNE 1234567890. Estimasi 2 hari."),
    ("rs-kontrol", "RS Harapan: Jadwal kontrol Ibu Siti besok pukul 09.00 di Poli Penyakit Dalam. Harap membawa kartu BPJS."),
    ("telkomsel-kuota", "Telkomsel: Kuota internet Anda tersisa 10%. Beli paket tambahan di aplikasi MyTelkomsel atau *363#."),
    ("kerja-bakti", "Info warga: Kerja bakti lingkungan hari Minggu pukul 07.00, mohon membawa alat kebersihan masing-masing."),
    ("tokopedia-sicepat", "Tokopedia: Pesanan Anda sudah dikirim dengan SiCepat. Lacak di aplikasi Tokopedia, bagian Transaksi."),
    ("bca-waspada", "BCA: Waspada penipuan! BCA tidak pernah meminta PIN, password, atau kode OTP Anda melalui telepon, SMS, atau media sosial."),
    ("ibu-jemput", "Ibu: Nak, besok jangan lupa jemput adik di sekolah jam 11 ya. Ibu pulang sore."),
    ("posyandu", "Dinas Kesehatan: Imunisasi gratis anak usia 0-5 tahun di Posyandu Melati, Sabtu 08.00-11.00. Bawa buku KIA."),
    ("ovo-bayar", "OVO: Pembayaran Rp 32.000 ke Alfamart berhasil. Saldo OVO Anda Rp 215.400."),
    ("wisuda", "Pengumuman kampus: Pendaftaran wisuda dibuka 1-10 November melalui portal akademik. Info lengkap di situs resmi universitas."),
    ("traveloka", "Traveloka: E-tiket Anda untuk penerbangan Jakarta-Surabaya, 20 Oktober 06.15, telah terbit. Cek email Anda."),
    ("pln-mobile", "PLN Mobile: Tagihan listrik bulan ini Rp 412.000. Jatuh tempo tanggal 20. Bayar lewat PLN Mobile atau bank mitra."),
    ("bengkel", "Hai, ini Budi dari bengkel. Motor Bapak sudah selesai diservis, bisa diambil kapan saja sampai jam 5 sore."),
    ("mama-eyang", "Mama: Besok Eyang datang dari Solo naik kereta. Papa yang jemput di stasiun jam 9 ya."),
    ("polsek-imbauan", "Polsek Setiabudi mengimbau warga agar waspada penipuan online. Laporkan ke 110 atau layanan resmi Polri jika menjadi korban."),
]
