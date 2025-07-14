# Geliştirici Kılavuzu

Bu belge, projeye katkı sağlamak isteyen geliştiriciler için derinlemesine teknik ayrıntılar içerir.

## 1. Mimarî Genel Bakış
main.pyw
├─ MainWindow # PyQt6 arayüz katmanı
│ ├─ init_ui() # Form bileşenleri
│ ├─ start_automation() # Thread & Worker başlatma
│ └─ log() # Zaman damgalı log yazımı
└─ WhatsAppWorker # Selenium iş parçacığı
├─ run() # Tarayıcı, profil, otomasyon döngüsü
├─ check_and_reply_messages()
└─ stop() # Güvenli durdurma

Ana iş yükü `WhatsAppWorker` sınıfının ayrı bir QThread üzerinde çalışmasıyla yönetilir. PyQt sinyal-slot mekanizması üzerinden UI ile haberleşir. :contentReference[oaicite:2]{index=2}

## 2. Başlıca Akış
1. **EdgeOptions** oluşturulur, profil dizini ayarlanır.  
2. EdgeDriver (varsa) `webdriver_manager` ile indirilir.  
3. WhatsApp Web yüklenir, QR doğrulaması tamamlanır.  
4. Saat aralığı denetimi → okunmamış sohbet taraması → mesaj yazımı → gönderim.  
5. Her döngü arasında `interval` × 60 saniye beklenir.

## 3. Ayarlar Şeması
```jsonc
{
  "message": "string",
  "start_time": "HH:MM",
  "end_time": "HH:MM",
  "interval": 1-1440,
  "excluded_contacts": ["Ad Soyad", "..."]
}
```
settings.json yüklenir, GUI alanlarına da yansıtılır. Değişiklikler save_settings() ile anında dosyaya yazılır.

## 4. Geliştirme Ortamı
Python 3.11 (PEP 660 uyumlu venv önerilir)

Edge 121+, WebDriver versiyon eşlenmeli

IDE olarak VS Code + black / ruff + pytest tavsiye edilir.

## 5. Test / Debug
```python
pytest -q                        # Birim testleri
python main.pyw --debug-log      # Ayrıntılı terminal logu
```
Uyarı: Selenium işlemi gerçek tarayıcı penceresinde ilerlediği için bilgisayar ve uygulama açık olmak zorunda.

