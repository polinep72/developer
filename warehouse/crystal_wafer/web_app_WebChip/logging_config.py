"""
Конфигурация логирования для Crystal Wafer Management System
Поддержка структурированного логирования в JSON формате и файлового логирования
"""
import json
import logging
import logging.handlers
import os
from datetime import datetime
from typing import Any, Dict, Optional


class JSONFormatter(logging.Formatter):
    """
    Форматтер для структурированного логирования в JSON формате
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Форматирует запись лога в JSON формат
        
        Args:
            record: Запись лога
            
        Returns:
            JSON строка с данными лога
        """
        log_entry: Dict[str, Any] = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'logger': record.name
        }
        
        # Добавляем дополнительные поля, если они есть
        if hasattr(record, 'user_id'):
            log_entry['user_id'] = getattr(record, 'user_id')  # type: ignore
        
        if hasattr(record, 'ip_address'):
            log_entry['ip_address'] = getattr(record, 'ip_address')  # type: ignore
        
        if hasattr(record, 'request_id'):
            log_entry['request_id'] = getattr(record, 'request_id')  # type: ignore
        
        if hasattr(record, 'endpoint'):
            log_entry['endpoint'] = getattr(record, 'endpoint')  # type: ignore
        
        if hasattr(record, 'method'):
            log_entry['method'] = getattr(record, 'method')  # type: ignore
        
        if hasattr(record, 'status_code'):
            log_entry['status_code'] = getattr(record, 'status_code')  # type: ignore
        
        if hasattr(record, 'duration_ms'):
            log_entry['duration_ms'] = getattr(record, 'duration_ms')  # type: ignore
        
        # Добавляем информацию об исключении, если есть
        if record.exc_info:
            log_entry['exception'] = self.formatException(record.exc_info)
        
        # Добавляем stack trace для DEBUG уровня
        if record.levelno == logging.DEBUG and record.exc_info is None:
            log_entry['stack_info'] = record.stack_info
        
        return json.dumps(log_entry, ensure_ascii=False, default=str)


class ExtendedFormatter(logging.Formatter):
    """
    Расширенный форматтер с дополнительными полями
    """
    
    def format(self, record: logging.LogRecord) -> str:
        """
        Форматирует запись лога с дополнительными полями
        
        Args:
            record: Запись лога
            
        Returns:
            Отформатированная строка лога
        """
        # Базовая информация
        parts = [
            self.formatTime(record, self.datefmt),
            record.levelname,
            f"{record.module}.{record.funcName}:{record.lineno}",
            record.getMessage()
        ]
        
        # Дополнительные поля
        extra_parts = []
        if hasattr(record, 'user_id'):
            extra_parts.append(f"user_id={getattr(record, 'user_id')}")  # type: ignore
        if hasattr(record, 'ip_address'):
            extra_parts.append(f"ip={getattr(record, 'ip_address')}")  # type: ignore
        if hasattr(record, 'request_id'):
            extra_parts.append(f"req_id={getattr(record, 'request_id')}")  # type: ignore
        if hasattr(record, 'endpoint'):
            extra_parts.append(f"endpoint={getattr(record, 'endpoint')}")  # type: ignore
        if hasattr(record, 'duration_ms'):
            extra_parts.append(f"duration={getattr(record, 'duration_ms')}ms")  # type: ignore
        
        if extra_parts:
            parts.append("[" + ", ".join(extra_parts) + "]")
        
        log_line = " - ".join(parts)
        
        # Добавляем информацию об исключении, если есть
        if record.exc_info:
            log_line += "\n" + self.formatException(record.exc_info)
        
        return log_line


def setup_logging(log_dir: Optional[str] = None, use_json: bool = False, log_level: str = "INFO"):
    """
    Настройка логирования для приложения
    
    Args:
        log_dir: Директория для логов (если None, используется logs/ в корне проекта)
        use_json: Использовать JSON формат для логов
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    # Определяем директорию для логов
    if log_dir is None:
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    
    # Создаем директорию для логов, если её нет
    os.makedirs(log_dir, exist_ok=True)
    
    # Получаем уровень логирования
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Настраиваем корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Очищаем существующие handlers (чтобы избежать дублирования)
    root_logger.handlers.clear()
    
    # Выбираем форматтер
    if use_json:
        formatter = JSONFormatter()
    else:
        formatter = ExtendedFormatter(
            fmt='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    # Консольный handler (всегда активен)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Файловый handler с ротацией (для всех логов)
    log_file = os.path.join(log_dir, 'app.log')
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=10,  # Хранить 10 файлов бэкапа
        encoding='utf-8'
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Файловый handler для ошибок (только ERROR и выше)
    error_log_file = os.path.join(log_dir, 'errors.log')
    error_handler = logging.handlers.RotatingFileHandler(
        error_log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=10,
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)
    
    # SMTP handler для критических ошибок (опционально)
    enable_email = os.getenv('ENABLE_EMAIL', 'true').lower().strip() == 'true'
    if enable_email:
        smtp_host = os.getenv('SMTP_HOST')
        smtp_port = int(os.getenv('SMTP_PORT', '587'))
        smtp_username = os.getenv('SMTP_USERNAME') or os.getenv('SMTP_USER')
        smtp_password = os.getenv('SMTP_PASSWORD')
        admin_email = os.getenv('ADMIN_EMAIL')
        from_email = os.getenv('SMTP_FROM_EMAIL', smtp_username)
        from_name = os.getenv('SMTP_FROM_NAME', 'Crystal Wafer Management System')
        smtp_use_tls = os.getenv('SMTP_USE_TLS', 'true').lower() == 'true'
        
        if smtp_host and smtp_username and smtp_password and admin_email:
            try:
                # Используем существующий SecureSMTPHandler из app.py
                # Импортируем его, если возможно, или создаем здесь
                # Для простоты, создадим базовый SMTP handler
                from email.mime.text import MIMEText
                from email.header import Header
                from email.utils import formatdate
                import smtplib
                
                class SecureSMTPHandler(logging.handlers.SMTPHandler):
                    def __init__(self, mailhost, fromaddr, toaddrs, subject, credentials, use_tls=True):
                        super().__init__(mailhost, fromaddr, toaddrs, subject, credentials)
                        self.use_tls = use_tls
                        self._sending = False
                        self.fromname = from_name
                    
                    def emit(self, record):
                        if self._sending:
                            return
                        try:
                            self._sending = True
                            port = self.mailport or smtplib.SMTP_PORT
                            smtp = smtplib.SMTP(self.mailhost, port)
                            if self.use_tls:
                                smtp.starttls()
                            if self.username:
                                smtp.login(self.username, self.password)
                            
                            msg = self.format(record)
                            from_header = f"{self.fromname} <{self.fromaddr}>" if self.fromname else self.fromaddr
                            
                            email_msg = MIMEText(msg, 'plain', 'utf-8')
                            email_msg['From'] = Header(from_header, 'utf-8')  # type: ignore
                            email_msg['To'] = Header(','.join(self.toaddrs), 'utf-8')  # type: ignore
                            email_msg['Subject'] = Header(self.getSubject(record), 'utf-8')  # type: ignore
                            email_msg['Date'] = formatdate()
                            
                            smtp.sendmail(self.fromaddr, self.toaddrs, email_msg.as_string())
                            smtp.quit()
                        except Exception as e:
                            import sys
                            print(f"ОШИБКА отправки email: {e}", file=sys.stderr)
                        finally:
                            self._sending = False
                
                smtp_handler = SecureSMTPHandler(
                    mailhost=(smtp_host, smtp_port),
                    fromaddr=from_email,
                    toaddrs=[admin_email],
                    subject='[КРИТИЧЕСКАЯ ОШИБКА] Crystal Wafer Management System',
                    credentials=(smtp_username, smtp_password),
                    use_tls=smtp_use_tls
                )
                smtp_handler.setLevel(logging.ERROR)
                smtp_handler.setFormatter(formatter)
                root_logger.addHandler(smtp_handler)
                root_logger.info(f"SMTP логирование настроено: {admin_email}")
            except Exception as e:
                root_logger.warning(f"Не удалось настроить SMTP логирование: {e}")
    
    root_logger.info(f"Логирование настроено: уровень={log_level}, JSON={use_json}, директория={log_dir}")

