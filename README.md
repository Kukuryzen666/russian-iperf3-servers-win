# ⚡ Russian iPerf3 SpeedTest CLI / TUI

[![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Rich TUI](https://img.shields.io/badge/UI-Rich%20TUI-brightgreen.svg)](https://github.com/Textualize/rich)
[![Original Project](https://img.shields.io/badge/upstream-itdoginfo%2Frussian--iperf3--servers-informational.svg)](https://github.com/itdoginfo/russian-iperf3-servers)

Улучшенный Python-клиент с современным интерактивным консольным интерфейсом (TUI) для замера скорости интернета и задержки (ping) до публичных серверов **iPerf3** в городах РФ.

Форк оригинального проекта [itdoginfo/russian-iperf3-servers](https://github.com/itdoginfo/russian-iperf3-servers).

---

## ✨ Возможности

- 🚀 **Интерактивный Live TUI на базе Rich**: живая таблица с индикацией статуса тестирования в реальном времени.
- 🎨 **Цветовая градация**: удобное цветовое выделение задержек (Ping) и пропускной способности (Download / Upload).
- 🔄 **Автоматический Fallback**: если основной сервер в городе недоступен, тест автоматически переключается на резервный сервер.
- ⚡ **Точный замер задержки (TCP Handshake Ping)**: рассчитывает время тройного рукопожатия TCP непосредственно до открытого порта iPerf3.
- 📊 **Итоговая сводка (Summary)**: подсчёт максимальной/средней скорости и лучшего сервера по пингу.
- 📁 **Экспорт результатов**: сохранение отчётов в форматах `JSON` или `CSV`.
- ⚙️ **Гибкая настройка**: выбор городов, изменение длительности замера, числа потоков и быстрый режим (2 сек).
- 💻 **Кроссплатформенность**: полная поддержка Windows (автоматическая настройка UTF-8), Linux и macOS.

---

## 🛠 Установка

### 1. Клонирование репозитория
```bash
git clone https://github.com/<ваш-логин>/russian-iperf3-servers.git
cd russian-iperf3-servers
```

### 2. Установка зависимостей Python
```bash
pip install -r requirements.txt
```

### 3. Установка утилиты iPerf3
Для работы скрипта требуется установленная утилита `iperf3`.

- **Windows**:
  - Через winget:
    ```powershell
    winget install iperf3
    ```
  - Или скачайте `iperf3.exe` с [официального сайта iperf.fr](https://iperf.fr/iperf-download.php) и поместите его в папку со скриптом (или добавьте в системный `PATH`).
- **Linux (Ubuntu / Debian)**:
  ```bash
  sudo apt update && sudo apt install iperf3
  ```
- **macOS (Homebrew)**:
  ```bash
  brew install iperf3
  ```

---

## 🚀 Использование

### Стандартный запуск
Запуск полного тестирования по всем серверам (длительность по 10 секунд на направление):
```bash
python speedtest.py
```

### Быстрый режим (`--fast` / `-f`)
Замер за 2 секунды на тест (удобно для экспресс-проверки):
```bash
python speedtest.py -f
```

### Тестирование выбранных городов (`--city` / `-c`)
```bash
python speedtest.py -c Moscow "Saint Petersburg"
```

### Настройка потоков и длительности
```bash
# 16 параллельных потоков, длительность 5 секунд на направление
python speedtest.py -P 16 -t 5
```

### Экспорт результатов в файл (`--export` / `-e`)
```bash
# Экспорт в JSON
python speedtest.py -e report.json

# Экспорт в CSV
python speedtest.py -e report.csv
```

### Вывод чистого JSON (для интеграций)
```bash
python speedtest.py --json
```

---

## 📋 Параметры командной строки

| Флаг | Описание | Значение по умолчанию |
|---|---|---|
| `-h`, `--help` | Показать справку по параметрам | — |
| `-f`, `--fast` | Быстрый режим тестирования (2 сек вместо 10) | `False` |
| `-t`, `--duration` | Длительность одного замера в секундах | `10` |
| `-P`, `--streams` | Количество параллельных потоков iperf3 | `8` |
| `-c`, `--city` | Список городов для замера (через пробел) | Все доступные |
| `-e`, `--export` | Путь для сохранения результатов (`.json` / `.csv`) | — |
| `--json` | Вывести только сырой JSON в stdout | `False` |
| `-d`, `--debug` | Включить подробный вывод отладки | `False` |

---

## 🌐 Список серверов

| Город | Основной сервер | Резервный сервер (Fallback) |
|---|---|---|
| **Москва** | `spd-rudp.hostkey.ru` | `st.tver.ertelecom.ru` (Тверь) |
| **Санкт-Петербург** | `st.spb.ertelecom.ru` | `st.yar.ertelecom.ru` (Ярославль) |
| **Нижний Новгород** | `st.nn.ertelecom.ru` | `speed-nn.vtt.net` |
| **Челябинск** | `st.chel.ertelecom.ru` | `st.mgn.ertelecom.ru` (Магнитогорск) |
| **Тюмень** | `st.tmn.ertelecom.ru` | `st.krsk.ertelecom.ru` (Красноярск) |

---

## 📜 Лицензия

Распространяется под лицензией [MIT](LICENSE).

Оригинальная база серверов предоставлена сообществом: [itdoginfo/russian-iperf3-servers](https://github.com/itdoginfo/russian-iperf3-servers).
