# External evaluation data (downloaded, not committed)

`python -m scripts.data.fetch` downloads these into this folder. They are real messages collected by other researchers;
none of them were used to write rules, prompts or tests, so they are an independent check on the checker.

| Folder | Source | What | Licence |
|---|---|---|---|
| `difraud_sms/` | [DIFrauD benchmark](https://huggingface.co/datasets/redasers/difraud) (Boyko et al., LREC-COLING 2024), `sms/test.jsonl` | 658 real SMS: the UCI SMS Spam Collection plus an SMS-phishing set from a UK wireless operator. `label` 1 = deceptive | MIT. Underlying UCI SMS Spam Collection: Almeida, Gómez Hidalgo & Yamakami (2011) |
| `mendeley_financial/` | [Financial scams detection dataset](https://data.mendeley.com/datasets/znsk27yk3h/2) (IUBAT, Mendeley Data, 2025) | 523 real scam / genuine financial messages (loan, job, OTP and bank-phishing scams vs. ordinary notices), English and Bangla; we use the English rows | CC BY 4.0 (credit the authors) |

Checked and **rejected**: DIFrauD `job_scams` (the "deceptive" examples read as ordinary job ads: noisy labels, and long postings are not messages),
DIFrauD `phishing` (long emails with off-topic junk in the deceptive class), `Shade63/scam-classification-multiclass` (no licence, no readable data files).

Caveats you should keep in mind when reading results: "spam" is not always "scam" (some labelled-deceptive texts are just advertising), the SMS data
is older (2003 to 2012 UK/Singapore/India), and the Mendeley messages were partly written by volunteers, so some look templated.
