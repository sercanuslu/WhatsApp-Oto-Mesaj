# WhatsApp Otomatik Mesaj Uygulaması

Python + PyQt6 + Selenium üçlüsüyle geliştirilen bu masaüstü uygulama, **WhatsApp Web** üzerinde gelen mesajları belirlediğin saat aralığında otomatik olarak yanıtlar.  
Bilgisayarın ve uygulamanın açık kalması gerekir; tarayıcı kapandığında yanıt işlemi durur. 

## 🚀 Öne Çıkan Özellikler
- **Saat Aralığı** : Başlangıç / bitiş saatini saniye hassasiyetinde ayarlayabilirsin.  
- **Kişi Hariç Tutma** : Yanıt gönderilmesini istemediğin kişileri listele.  
- **Süreli Kontrol** : Mesaj kutusu tarama periyodunu (dakika) kendin seç.  
- **Sistem Tepsisi** : Uygulama kapansa bile arka planda çalışmaya devam eder.  

## 💾 Gereksinimler
| Bileşen | Minimum Sürüm |
|---------|---------------|
| Python  | 3.11 |
| PyQt6   | 6.6 |
| Selenium| 4.20 |
| Microsoft Edge & WebDriver | Güncel sürüm |

> **Not:** `webdriver_manager` kuruluysa EdgeDriver otomatik indirilir; değilse el ile eklemelisin. :contentReference[oaicite:0]{index=0}

## 🔧 Kurulum
```bash
git clone https://github.com/sercanuslu/WhatsApp-Oto-Mesaj.git
cd whatsapp-oto-mesaj
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.pyw
