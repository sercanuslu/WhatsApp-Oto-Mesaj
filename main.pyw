import sys
import os
import json
import time
import re
from datetime import datetime, time as dt_time

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QTextEdit, QPushButton, QTimeEdit, QSpinBox,
                             QSystemTrayIcon, QMenu, QMessageBox, QFormLayout)
from PyQt6.QtGui import QIcon, QAction
from PyQt6.QtCore import QThread, QObject, pyqtSignal, QTime, Qt

from selenium import webdriver
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (TimeoutException, NoSuchElementException, 
                                        StaleElementReferenceException, WebDriverException)
from selenium.webdriver.common.action_chains import ActionChains

# --- Sabitler ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")
ICON_PATH = os.path.join(BASE_DIR, "icons", "tray_icon.png")
EDGE_PROFILE_PATH = os.path.join(BASE_DIR, "edge_profile")
WHATSAPP_URL = "https://web.whatsapp.com/"

# EdgeDriver'ı otomatik indir ve yönet
try:
    from webdriver_manager.microsoft import EdgeChromiumDriverManager
    USE_DRIVER_MANAGER = True
except ImportError:
    USE_DRIVER_MANAGER = False


class WhatsAppWorker(QObject):
    """
    Selenium ile WhatsApp otomasyonunu ayrı bir thread'de yürüten,
    hatalara karşı güçlendirilmiş ve detaylı loglama yapan sınıf.
    """
    log_message = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self._is_running = True
        self.driver = None
        self.replied_contacts_today = set()

    def run(self):
        """Ana otomasyon döngüsü."""
        self.log_message.emit("Otomasyon motoru başlatılıyor...")
        self.log_message.emit("Not: Sorun yaşanırsa, uygulamayı kapatıp 'edge_profile' klasörünü silin.")
        self.replied_contacts_today.clear()
        self.log_message.emit("Bugünkü yanıt listesi temizlendi.")
        
        try:
            self.log_message.emit("1/4: Edge tarayıcı seçenekleri ayarlanıyor...")
            options = webdriver.EdgeOptions()
            options.add_argument("--start-maximized")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_argument(f"--user-data-dir={EDGE_PROFILE_PATH}")
            # Çökme sorununu önlemek için ek argümanlar
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--disable-features=VizDisplayCompositor")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-blink-features=AutomationControlled")
            # Bellek kullanımını optimize et
            options.add_argument("--memory-pressure-off")
            options.add_argument("--max_old_space_size=4096")

            self.log_message.emit("2/4: Edge WebDriver servisi başlatılıyor...")
            # Profil dizini yoksa oluştur
            if not os.path.exists(EDGE_PROFILE_PATH):
                os.makedirs(EDGE_PROFILE_PATH)
                self.log_message.emit("Edge profil dizini oluşturuldu.")
            
            # EdgeDriver'ı otomatik yönet
            if USE_DRIVER_MANAGER:
                try:
                    self.log_message.emit("EdgeDriver otomatik indiriliyor/güncelleniyor...")
                    service = EdgeService(EdgeChromiumDriverManager().install())
                except Exception as e:
                    self.log_message.emit(f"EdgeDriver otomatik yönetimi başarısız: {e}")
                    self.log_message.emit("Sistem EdgeDriver kullanılıyor...")
                    service = EdgeService()
            else:
                service = EdgeService()

            self.log_message.emit("3/4: Edge tarayıcı örneği oluşturuluyor...")
            try:
                self.driver = webdriver.Edge(service=service, options=options)
            except Exception as e:
                self.log_message.emit("İlk deneme başarısız, profil olmadan deneniyor...")
                # Profil sorunu varsa profil olmadan dene
                options = webdriver.EdgeOptions()
                options.add_argument("--start-maximized")
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument("--disable-gpu")
                options.add_argument("--disable-features=VizDisplayCompositor")
                self.driver = webdriver.Edge(service=service, options=options)

            self.log_message.emit(f"4/4: WhatsApp Web adresine gidiliyor: {WHATSAPP_URL}")
            self.driver.get(WHATSAPP_URL)

            # WhatsApp Web yüklenene kadar bekle
            self.log_message.emit("WhatsApp Web yükleniyor, QR kod veya otomatik giriş bekleniyor...")
            WebDriverWait(self.driver, 300).until(
                EC.presence_of_element_located((By.ID, "side"))
            )
            self.log_message.emit("Giriş başarılı! Mesaj kontrol döngüsü başlıyor.")
            
            # İlk yüklemeden sonra biraz bekle
            time.sleep(5)
            
            while self._is_running:
                self.check_and_reply_messages()
                for i in range(self.settings['interval'] * 60):
                    if not self._is_running: break
                    time.sleep(1)

        except WebDriverException as e:
            self.log_message.emit(f"TARAYICI HATASI: {str(e).splitlines()[0]}")
        except TimeoutException:
            self.log_message.emit("HATA: Giriş zaman aşımına uğradı (5 dakika).")
        except Exception as e:
            self.log_message.emit(f"KRİTİK HATA: {type(e).__name__}: {e}")
        finally:
            if self.driver:
                self.driver.quit()
            self.log_message.emit("Otomasyon durduruldu. Tarayıcı kapatıldı.")
            self.finished.emit()

    def check_and_reply_messages(self):
        """Okunmamış mesajları en sağlam yöntemle tespit eder ve yanıtlar."""
        try:
            now = datetime.now().time()
            start_time = self.settings['start_time']
            end_time = self.settings['end_time']

            is_active = False
            if start_time > end_time:
                if now >= start_time or now <= end_time: is_active = True
            else:
                if start_time <= now <= end_time: is_active = True
            
            if not is_active:
                return

            self.log_message.emit("Sohbet listesi taranıyor...")
            
            # Sohbet listesi konteynerini bul
            chat_list_container = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, 'div[aria-label="Sohbet listesi"]'))
            )
            
            # Okunmamış mesajları bul - yeni HTML yapısına göre güncellendi
            unread_chats = []
            try:
                # Tüm sohbet öğelerini bul
                all_chats = chat_list_container.find_elements(By.CSS_SELECTOR, 'div[role="listitem"]')
                
                for chat in all_chats:
                    try:
                        # Okunmamış mesaj göstergesini ara
                        unread_indicator = chat.find_element(By.CSS_SELECTOR, 'span[aria-label*="okunmamış"], span[aria-label*="unread"]')
                        if unread_indicator:
                            unread_chats.append(chat)
                    except NoSuchElementException:
                        continue
            except Exception as e:
                self.log_message.emit(f"Sohbet listesi taranırken hata: {e}")

            if not unread_chats:
                self.log_message.emit("Yeni mesaj bulunamadı.")
                return

            self.log_message.emit(f"{len(unread_chats)} adet okunmamış sohbet bulundu.")

            chats_to_process = []
            for chat in unread_chats:
                try:
                    # Kişi adını bul
                    sender_element = chat.find_element(By.CSS_SELECTOR, 'span[dir="auto"][title]')
                    sender_name = sender_element.get_attribute("title")
                    if sender_name:
                        chats_to_process.append((sender_name, chat))
                except NoSuchElementException:
                    continue
            
            for sender_name, chat_element in chats_to_process:
                if not self._is_running: break
                
                try:
                    if sender_name in self.replied_contacts_today or sender_name in self.settings['excluded_contacts']:
                        continue

                    self.log_message.emit(f"'{sender_name}' sohbetine tıklanıyor...")
                    
                    # Direkt chat elementine tıkla
                    try:
                        ActionChains(self.driver).move_to_element(chat_element).click().perform()
                    except Exception:
                        # Alternatif: JavaScript ile tıkla
                        self.driver.execute_script("arguments[0].click();", chat_element)
                    
                    time.sleep(2)  # Sohbetin açılması için bekle

                    # Sohbetin açıldığını doğrula - farklı yöntemlerle
                    self.log_message.emit("Sohbetin açılması doğrulanıyor...")
                    header_loaded = False
                    
                    # Yöntem 1: Başlıkta kişi adını ara
                    for i in range(10):
                        try:
                            # Önce genel başlık alanını bul
                            header = self.driver.find_element(By.CSS_SELECTOR, 'header[data-testid="conversation-header"], div[data-testid="conversation-header"], header')
                            # Başlıkta kişi adını içeren span'i ara
                            header_name = header.find_element(By.XPATH, f'.//span[contains(@title, "{sender_name}") or contains(text(), "{sender_name}")]')
                            if header_name:
                                header_loaded = True
                                self.log_message.emit("Sohbet başlığı doğrulandı.")
                                break
                        except NoSuchElementException:
                            pass
                        
                        # Yöntem 2: Mesaj alanının görünür olup olmadığını kontrol et
                        try:
                            self.driver.find_element(By.CSS_SELECTOR, 'footer, div[data-testid="conversation-panel-messages"]')
                            header_loaded = True
                            self.log_message.emit("Sohbet paneli doğrulandı.")
                            break
                        except NoSuchElementException:
                            time.sleep(1)
                    
                    if not header_loaded:
                        self.log_message.emit(f"HATA: '{sender_name}' sohbeti açılamadı.")
                        continue

                    # Mesaj kutusu aranıyor - güncellenmiş seçiciler
                    self.log_message.emit("Mesaj kutusu aranıyor...")
                    message_box = None
                    
                    # Farklı mesaj kutusu seçicileri
                    message_box_selectors = [
                        'div[contenteditable="true"][data-tab="10"]',
                        'div[contenteditable="true"][role="textbox"]',
                        'div[data-testid="conversation-compose-box-input"]',
                        'footer div[contenteditable="true"]',
                        'div[title="Bir mesaj yazın"]',
                        'div[data-lexical-editor="true"]',
                        'p[class*="selectable-text"]'
                    ]
                    
                    for selector in message_box_selectors:
                        try:
                            elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                            for elem in elements:
                                if elem.is_displayed() and elem.is_enabled():
                                    message_box = elem
                                    self.log_message.emit(f"Mesaj kutusu bulundu: {selector}")
                                    break
                            if message_box:
                                break
                        except Exception:
                            continue
                    
                    if not message_box:
                        # Son çare: footer içindeki tüm contenteditable elementleri dene
                        try:
                            footer = self.driver.find_element(By.TAG_NAME, 'footer')
                            editables = footer.find_elements(By.CSS_SELECTOR, '[contenteditable="true"]')
                            for editable in editables:
                                if editable.is_displayed():
                                    message_box = editable
                                    self.log_message.emit("Mesaj kutusu footer'da bulundu.")
                                    break
                        except Exception:
                            pass
                    
                    if not message_box:
                        self.log_message.emit(f"HATA: '{sender_name}' için mesaj kutusu bulunamadı.")
                        continue
                    
                    # Mesaj kutusuna odaklan ve mesaj gönder
                    self.log_message.emit("Mesaj gönderiliyor...")
                    
                    # Önce mesaj kutusuna tıkla ve odaklan
                    try:
                        ActionChains(self.driver).move_to_element(message_box).click().perform()
                    except Exception:
                        self.driver.execute_script("arguments[0].focus();", message_box)
                        self.driver.execute_script("arguments[0].click();", message_box)
                    
                    time.sleep(0.5)
                    
                    # Mesajı yaz ve gönder
                    try:
                        # Önce kutunun içeriğini temizle
                        message_box.clear()
                        time.sleep(0.2)
                        
                        # Mesajı yaz
                        message_box.send_keys(self.settings['message'])
                        time.sleep(0.5)
                        
                        # Enter'a bas
                        message_box.send_keys(Keys.ENTER)
                        
                        self.log_message.emit(f"'{sender_name}' kişisine mesaj gönderildi.")
                        self.replied_contacts_today.add(sender_name)
                        
                    except Exception as e:
                        # Alternatif yöntem: JavaScript ile mesaj gönder
                        self.log_message.emit("JavaScript yöntemi deneniyor...")
                        try:
                            # Mesajı JavaScript ile yaz
                            self.driver.execute_script(
                                """
                                var messageBox = arguments[0];
                                var message = arguments[1];
                                messageBox.innerHTML = message;
                                messageBox.textContent = message;
                                
                                // Input event'i tetikle
                                var inputEvent = new Event('input', { bubbles: true });
                                messageBox.dispatchEvent(inputEvent);
                                
                                // Change event'i tetikle
                                var changeEvent = new Event('change', { bubbles: true });
                                messageBox.dispatchEvent(changeEvent);
                                """, 
                                message_box, 
                                self.settings['message']
                            )
                            time.sleep(0.5)
                            
                            # Enter tuşuna bas
                            message_box.send_keys(Keys.ENTER)
                            
                            self.log_message.emit(f"'{sender_name}' kişisine mesaj gönderildi (JS).")
                            self.replied_contacts_today.add(sender_name)
                            
                        except Exception as js_error:
                            self.log_message.emit(f"Mesaj gönderilemedi: {js_error}")
                            continue
                    
                    # Mesaj gönderildikten sonra bekle
                    time.sleep(3)

                except Exception as e:
                    self.log_message.emit(f"Hata ('{sender_name}' yanıtlanırken): {type(e).__name__} - {str(e)}")

        except Exception as e:
            self.log_message.emit(f"Hata (dış döngü): {type(e).__name__} - {str(e)}")

    def stop(self):
        self._is_running = False
        self.log_message.emit("Durdurma sinyali alındı...")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WhatsApp Otomatik Mesaj")
        self.setWindowIcon(QIcon(ICON_PATH))
        self.setMinimumSize(600, 500)
        self.thread = None
        self.worker = None
        self.init_ui()
        self.init_tray_icon()
        self.load_settings()

    def init_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        form_layout = QFormLayout()
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Gönderilecek otomatik mesajı buraya yazın")
        self.start_time_input = QTimeEdit()
        self.start_time_input.setDisplayFormat("HH:mm")
        self.end_time_input = QTimeEdit()
        self.end_time_input.setDisplayFormat("HH:mm")
        self.interval_input = QSpinBox()
        self.interval_input.setMinimum(1)
        self.interval_input.setMaximum(1440)
        self.interval_input.setSuffix(" dakika")
        self.excluded_input = QTextEdit()
        self.excluded_input.setPlaceholderText("Mesaj gönderilmeyecek kişilerin adlarını alt alta yazın.")
        form_layout.addRow(QLabel("Otomatik Mesaj:"), self.message_input)
        time_layout = QHBoxLayout()
        time_layout.addWidget(self.start_time_input)
        time_layout.addWidget(QLabel("-"))
        time_layout.addWidget(self.end_time_input)
        form_layout.addRow(QLabel("Aktif Saat Aralığı:"), time_layout)
        form_layout.addRow(QLabel("Kontrol Sıklığı:"), self.interval_input)
        form_layout.addRow(QLabel("Yasaklı Kişiler:"), self.excluded_input)
        main_layout.addLayout(form_layout)
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Otomasyonu Başlat")
        self.start_button.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px; border-radius: 5px;")
        self.start_button.clicked.connect(self.start_automation)
        self.stop_button = QPushButton("Otomasyonu Durdur")
        self.stop_button.setStyleSheet("background-color: #f44336; color: white; padding: 10px; border-radius: 5px;")
        self.stop_button.clicked.connect(self.stop_automation)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        main_layout.addLayout(button_layout)
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        main_layout.addWidget(QLabel("Gerçek Zamanlı Loglar:"))
        main_layout.addWidget(self.log_output)

    def init_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable(): return
        self.tray_icon = QSystemTrayIcon(QIcon(ICON_PATH), self)
        self.tray_icon.setToolTip("WhatsApp Otomatik Mesaj")
        tray_menu = QMenu()
        show_action = QAction("Göster", self)
        show_action.triggered.connect(self.show_window)
        quit_action = QAction("Çıkış", self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        self.tray_icon.activated.connect(self.on_tray_icon_activated)

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window()

    def show_window(self):
        self.show()
        self.activateWindow()
        self.raise_()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)

    def log(self, message):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_output.append(f"[{timestamp}] {message}")

    def load_settings(self):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self.message_input.setText(settings.get("message", ""))
                    self.start_time_input.setTime(QTime.fromString(settings.get("start_time", "09:00"), "HH:mm"))
                    self.end_time_input.setTime(QTime.fromString(settings.get("end_time", "18:00"), "HH:mm"))
                    self.interval_input.setValue(settings.get("interval", 5))
                    self.excluded_input.setText("\n".join(settings.get("excluded_contacts", [])))
                self.log("Ayarlar başarıyla yüklendi.")
        except Exception as e:
            self.log(f"Ayarları yüklerken hata oluştu: {e}")

    def save_settings(self):
        settings = {
            "message": self.message_input.text(),
            "start_time": self.start_time_input.time().toString("HH:mm"),
            "end_time": self.end_time_input.time().toString("HH:mm"),
            "interval": self.interval_input.value(),
            "excluded_contacts": [line.strip() for line in self.excluded_input.toPlainText().splitlines() if line.strip()]
        }
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
            self.log("Ayarlar başarıyla kaydedildi.")
            return settings
        except Exception as e:
            self.log(f"Ayarları kaydederken hata oluştu: {e}")
            return None

    def start_automation(self):
        settings_data = self.save_settings()
        if not settings_data: return
        if not settings_data.get("message"):
            QMessageBox.warning(self, "Eksik Bilgi", "Lütfen gönderilecek bir mesaj girin.")
            return
        worker_settings = {
            'message': settings_data['message'],
            'start_time': dt_time.fromisoformat(settings_data['start_time']),
            'end_time': dt_time.fromisoformat(settings_data['end_time']),
            'interval': settings_data['interval'],
            'excluded_contacts': settings_data['excluded_contacts']
        }
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.log("Otomasyon başlatılıyor...")
        self.thread = QThread()
        self.worker = WhatsAppWorker(worker_settings)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_automation_finished)
        self.worker.log_message.connect(self.log)
        self.thread.start()

    def stop_automation(self):
        if self.worker:
            self.worker.stop()
        self.log("Otomasyon durduruluyor, lütfen bekleyin...")

    def on_automation_finished(self):
        if self.thread and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()
        self.thread = None
        self.worker = None
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.log("Otomasyon başarıyla sonlandırıldı.")

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray_icon.showMessage(
            "Uygulama Çalışıyor",
            "WhatsApp Otomatik Mesaj uygulaması arka planda çalışmaya devam ediyor.",
            QSystemTrayIcon.MessageIcon.Information,
            2000
        )

    def quit_app(self):
        self.log("Uygulamadan çıkılıyor...")
        self.stop_automation()
        if self.thread:
            self.thread.wait(5000)
        self.tray_icon.hide()
        QApplication.instance().quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    if not os.path.exists(ICON_PATH):
        QMessageBox.critical(None, "Hata", f"Simge dosyası bulunamadı!\nBeklenen konum: {ICON_PATH}")
        sys.exit(1)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())