import argparse
import glob
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict

# Fix Windows console UTF-8 output encoding for emojis and rich styling
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.live import Live
from rich.layout import Layout
from rich.text import Text
from rich.align import Align
from rich import box

# --- Configuration ---
DEFAULT_TIMEOUT = 15
DEFAULT_TEST_DURATION = 10
DEFAULT_PARALLEL_STREAMS = 8
FALLBACK_STREAMS = 8
INTER_TEST_DELAY = 0.5

IPERF_PORT_RANGE = [5201, 5202, 5203, 5204, 5205, 5206, 5207, 5208, 5209]

SERVERS: Dict[str, str] = {
    "Moscow": "spd-rudp.hostkey.ru",
    "Saint Petersburg": "st.spb.ertelecom.ru",
    "Nizhny Novgorod": "st.nn.ertelecom.ru",
    "Chelyabinsk": "st.chel.ertelecom.ru",
    "Tyumen": "st.tmn.ertelecom.ru",
}

FALLBACK_SERVERS: Dict[str, str] = {
    "Moscow": "st.tver.ertelecom.ru",
    "Saint Petersburg": "st.yar.ertelecom.ru",
    "Nizhny Novgorod": "speed-nn.vtt.net",
    "Chelyabinsk": "st.mgn.ertelecom.ru",
    "Tyumen": "st.krsk.ertelecom.ru",
}

FALLBACK_CITIES: Dict[str, str] = {
    "Moscow": "Tver",
    "Saint Petersburg": "Yaroslavl",
    "Nizhny Novgorod": "Nizhny Novgorod",
    "Chelyabinsk": "Magnitogorsk",
    "Tyumen": "Krasnoyarsk",
}

CITY_ORDER: List[str] = [
    "Moscow",
    "Saint Petersburg",
    "Nizhny Novgorod",
    "Chelyabinsk",
    "Tyumen"
]


@dataclass
class TestResult:
    city: str
    host: str
    port: Optional[int]
    download_mbps: float
    upload_mbps: float
    ping_ms: Optional[int]
    status: str  # "ONLINE", "FALLBACK", "OFFLINE", "PENDING", "TESTING"
    is_fallback: bool = False
    error: Optional[str] = None


class SpeedTester:
    def __init__(
        self,
        duration: int = DEFAULT_TEST_DURATION,
        streams: int = DEFAULT_PARALLEL_STREAMS,
        debug: bool = False,
        fast_mode: bool = False,
        selected_cities: Optional[List[str]] = None,
        export_file: Optional[str] = None,
        json_output: bool = False
    ):
        self.console = Console()
        self.debug = debug
        self.duration = 2 if fast_mode else duration
        self.streams = streams
        self.fast_mode = fast_mode
        self.export_file = export_file
        self.json_output = json_output
        self.cities = selected_cities if selected_cities else CITY_ORDER
        self.results: Dict[str, TestResult] = {}
        self.iperf_cmd: Optional[str] = self.find_iperf3_command()
        
        # Initialize result status
        for city in self.cities:
            if city in SERVERS:
                self.results[city] = TestResult(
                    city=city,
                    host=SERVERS[city],
                    port=None,
                    download_mbps=0.0,
                    upload_mbps=0.0,
                    ping_ms=None,
                    status="PENDING"
                )

    def log_debug(self, message: str) -> None:
        if self.debug:
            self.console.print(f"[dim grey50][DEBUG][/] {message}")

    def find_iperf3_command(self) -> Optional[str]:
        # 1. PyInstaller bundled path (_MEIPASS)
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            bundled = os.path.join(sys._MEIPASS, "iperf3.exe")
            if os.path.isfile(bundled):
                return bundled

        # 2. Next to executable / script
        base_dir = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))
        candidate = os.path.join(base_dir, "iperf3.exe" if sys.platform.startswith("win") else "iperf3")
        if os.path.isfile(candidate):
            return candidate

        # 3. System PATH
        path_cmd = shutil.which("iperf3")
        if path_cmd:
            return path_cmd

        # 4. Standard WinGet / LocalAppData paths on Windows
        if sys.platform.startswith("win"):
            local_app_data = os.environ.get("LOCALAPPDATA", "")
            if local_app_data:
                winget_glob = os.path.join(local_app_data, "Microsoft", "WinGet", "Packages", "*iperf3*", "iperf3.exe")
                matches = glob.glob(winget_glob)
                if matches:
                    return matches[0]

        return None

    def check_iperf3_installed(self) -> bool:
        if not self.iperf_cmd:
            return False
        try:
            subprocess.run(
                [self.iperf_cmd, "-v"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True
        except (FileNotFoundError, OSError):
            return False

    def find_available_port(self, host: str) -> Optional[int]:
        self.log_debug(f"Scanning ports for {host}")
        for port in IPERF_PORT_RANGE:
            try:
                with socket.create_connection((host, port), timeout=1.5):
                    self.log_debug(f"Found active port {port} on {host}")
                    return port
            except (socket.timeout, ConnectionRefusedError, OSError):
                continue
        return None

    def get_tcp_ping(self, host: str, port: int) -> Optional[int]:
        """Calculates latency via 3 TCP connection handshakes."""
        try:
            times = []
            for _ in range(3):
                start = time.perf_counter()
                with socket.create_connection((host, port), timeout=2.0):
                    pass
                times.append(time.perf_counter() - start)
            return int((sum(times) / len(times)) * 1000)
        except Exception:
            return None

    def run_iperf_test(self, host: str, port: int, streams: int, reverse: bool = False) -> float:
        """Executes iperf3 test and returns Mbps."""
        if not self.iperf_cmd:
            return 0.0

        cmd = [
            self.iperf_cmd,
            "-c", host,
            "-p", str(port),
            "-P", str(streams),
            "-t", str(self.duration),
            "--json"
        ]
        if reverse:
            cmd.append("-R")

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=DEFAULT_TIMEOUT + self.duration
            )
            if res.returncode == 0 and res.stdout:
                data = json.loads(res.stdout)
                bits = data["end"]["sum_received"]["bits_per_second"]
                return round(bits / 1_000_000, 2)
        except subprocess.TimeoutExpired:
            self.log_debug(f"iperf3 timed out on {host}:{port}")
        except json.JSONDecodeError:
            self.log_debug(f"Failed to parse iperf3 JSON on {host}:{port}")
        except Exception as e:
            self.log_debug(f"Test error on {host}:{port} -> {e}")

        return 0.0

    def generate_table(self, current_action: str = "") -> Table:
        table = Table(
            box=box.ROUNDED,
            show_header=True,
            header_style="bold bright_white on grey23",
            border_style="bright_blue"
        )

        table.add_column("Город", style="bold white", no_wrap=True)
        table.add_column("Сервер", style="cyan", overflow="fold")
        table.add_column("Пинг", justify="center", no_wrap=True)
        table.add_column("Download", justify="right", no_wrap=True)
        table.add_column("Upload", justify="right", no_wrap=True)
        table.add_column("Статус", justify="center", no_wrap=True)

        for city, res in self.results.items():
            # City representation
            city_display = f"[bold]{city}[/]"
            if res.is_fallback:
                city_display = f"[yellow]{res.city} [dim](FB)[/][/]"

            # Host representation
            host_display = f"{res.host}:{res.port}" if res.port else f"{res.host}"

            # Ping representation
            if res.ping_ms is not None:
                if res.ping_ms < 25:
                    ping_str = f"[bold green]{res.ping_ms} ms[/]"
                elif res.ping_ms < 60:
                    ping_str = f"[bold yellow]{res.ping_ms} ms[/]"
                else:
                    ping_str = f"[bold red]{res.ping_ms} ms[/]"
            elif res.status in ("OFFLINE", "ERROR"):
                ping_str = "[dim red]N/A[/]"
            elif res.status == "TESTING":
                ping_str = "[dim cyan]...[/]"
            else:
                ping_str = "[dim grey50]—[/]"

            # Download representation
            if res.download_mbps > 0:
                if res.download_mbps >= 300:
                    dl_str = f"[bold bright_green]{res.download_mbps:,.1f} Mbps[/]"
                elif res.download_mbps >= 100:
                    dl_str = f"[bold green]{res.download_mbps:,.1f} Mbps[/]"
                elif res.download_mbps >= 30:
                    dl_str = f"[bold yellow]{res.download_mbps:,.1f} Mbps[/]"
                else:
                    dl_str = f"[bold red]{res.download_mbps:,.1f} Mbps[/]"
            elif res.status == "TESTING" and "Download" in current_action:
                dl_str = "[bold cyan]⏳ Тест...[/]"
            elif res.status in ("OFFLINE", "ERROR"):
                dl_str = "[bold red]—[/]"
            else:
                dl_str = "[dim grey50]—[/]"

            # Upload representation
            if res.upload_mbps > 0:
                if res.upload_mbps >= 300:
                    ul_str = f"[bold bright_green]{res.upload_mbps:,.1f} Mbps[/]"
                elif res.upload_mbps >= 100:
                    ul_str = f"[bold green]{res.upload_mbps:,.1f} Mbps[/]"
                elif res.upload_mbps >= 30:
                    ul_str = f"[bold yellow]{res.upload_mbps:,.1f} Mbps[/]"
                else:
                    ul_str = f"[bold red]{res.upload_mbps:,.1f} Mbps[/]"
            elif res.status == "TESTING" and "Upload" in current_action:
                ul_str = "[bold magenta]⏳ Тест...[/]"
            elif res.status in ("OFFLINE", "ERROR"):
                ul_str = "[bold red]—[/]"
            else:
                ul_str = "[dim grey50]—[/]"

            # Status column
            if res.status == "ONLINE":
                status_str = "[bold green]✔ OK[/]"
            elif res.status == "FALLBACK":
                status_str = "[bold yellow]⚠ FALLBACK[/]"
            elif res.status == "OFFLINE":
                status_str = "[bold red]✖ OFFLINE[/]"
            elif res.status == "TESTING":
                status_str = "[bold bright_cyan]● ТЕСТ...[/]"
            else:
                status_str = "[dim grey50]○ ОЖИДАНИЕ[/]"

            table.add_row(
                city_display,
                host_display,
                ping_str,
                dl_str,
                ul_str,
                status_str
            )

        return table

    def render_header(self) -> Panel:
        title_text = Text.from_markup(
            "[bold bright_cyan]⚡ Russian iPerf3 SpeedTest[/] "
            "[dim]— Измерение скорости интернета в РФ[/]\n"
            "[blue]🌐 https://github.com/itdoginfo/russian-iperf3-servers[/]"
        )
        
        info_sub = (
            f"[bright_white]Параметры:[/] Длительность: [bold green]{self.duration}с[/] | "
            f"Потоки: [bold green]{self.streams}[/] | "
            f"Режим: [{'bold yellow' if self.fast_mode else 'bold cyan'}]{'Быстрый (Fast)' if self.fast_mode else 'Стандартный'}[/]"
        )
        
        content = Text.assemble(
            title_text,
            "\n\n",
            Text.from_markup(info_sub)
        )

        return Panel(
            content,
            box=box.ROUNDED,
            border_style="cyan",
            padding=(1, 2)
        )

    def render_summary(self, elapsed_seconds: float) -> Panel:
        valid_dl = [r for r in self.results.values() if r.download_mbps > 0]
        valid_ul = [r for r in self.results.values() if r.upload_mbps > 0]
        pinged = [r for r in self.results.values() if r.ping_ms is not None and (r.download_mbps > 0 or r.upload_mbps > 0)]
        
        if not valid_dl and not valid_ul:
            return Panel(
                "[bold red]✖ Не удалось получить результаты ни с одного сервера.[/]",
                box=box.ROUNDED,
                border_style="red",
                title="[bold red]Итоги теста[/]"
            )

        best_dl = max(valid_dl, key=lambda x: x.download_mbps) if valid_dl else None
        best_ul = max(valid_ul, key=lambda x: x.upload_mbps) if valid_ul else None
        best_ping = min(pinged, key=lambda x: x.ping_ms) if pinged else None

        avg_dl = (sum(r.download_mbps for r in valid_dl) / len(valid_dl)) if valid_dl else 0.0
        avg_ul = (sum(r.upload_mbps for r in valid_ul) / len(valid_ul)) if valid_ul else 0.0

        summary_text = f"[bold bright_white]📊 Сводные показатели за {int(elapsed_seconds)} сек:[/]\n\n"
        
        if best_dl:
            summary_text += f"  🚀 [bold cyan]Макс. Download:[/]   [bold bright_green]{best_dl.download_mbps:,.1f} Mbps[/] [dim]({best_dl.city})[/]\n"
        else:
            summary_text += f"  🚀 [bold cyan]Макс. Download:[/]   [dim red]—[/]\n"
            
        if best_ul:
            summary_text += f"  📤 [bold magenta]Макс. Upload:[/]     [bold bright_green]{best_ul.upload_mbps:,.1f} Mbps[/] [dim]({best_ul.city})[/]\n"
        else:
            summary_text += f"  📤 [bold magenta]Макс. Upload:[/]     [dim red]—[/]\n"

        if best_ping and best_ping.ping_ms is not None:
            summary_text += f"  ⚡ [bold yellow]Мин. Пинг (RTT):[/]   [bold bright_green]{best_ping.ping_ms} ms[/] [dim]({best_ping.city})[/]\n"

        summary_text += (
            f"\n  📈 [dim]Средний Download:[/] [bold white]{avg_dl:,.1f} Mbps[/] | "
            f"[dim]Средний Upload:[/] [bold white]{avg_ul:,.1f} Mbps[/]"
        )

        return Panel(
            summary_text,
            box=box.ROUNDED,
            border_style="bright_green",
            title="[bold bright_green]✔ Тестирование завершено[/]",
            padding=(1, 2)
        )

    def test_single_server(
        self,
        city: str,
        host: str,
        is_fallback: bool = False,
        progress_cb=None
    ) -> bool:
        res = self.results[city]
        res.status = "TESTING"
        res.is_fallback = is_fallback
        res.host = host
        
        if progress_cb:
            progress_cb(f"Поиск открытого порта для {host}...")
            
        port = self.find_available_port(host)
        if not port:
            return False

        res.port = port

        # Step 1: Ping
        if progress_cb:
            progress_cb(f"Замер TCP Ping для {host}:{port}...")
        ping_val = self.get_tcp_ping(host, port)
        res.ping_ms = ping_val

        # Step 2: Download Test
        if progress_cb:
            progress_cb(f"⬇ Тест Download на {host}:{port} ({self.streams} потоков)...")
        dl = self.run_iperf_test(host, port, self.streams, reverse=True)
        res.download_mbps = dl

        # Step 3: Upload Test
        if progress_cb:
            progress_cb(f"⬆ Тест Upload на {host}:{port} ({self.streams} потоков)...")
        ul = self.run_iperf_test(host, port, self.streams, reverse=False)
        res.upload_mbps = ul

        # Fallback stream retry if 0
        if dl == 0.0 and ul == 0.0:
            if progress_cb:
                progress_cb(f"Повтор с {FALLBACK_STREAMS} потоками...")
            dl = self.run_iperf_test(host, port, FALLBACK_STREAMS, reverse=True)
            ul = self.run_iperf_test(host, port, FALLBACK_STREAMS, reverse=False)
            res.download_mbps = dl
            res.upload_mbps = ul

        if dl > 0.0 or ul > 0.0:
            res.status = "FALLBACK" if is_fallback else "ONLINE"
            return True

        return False

    def export_data(self) -> None:
        if not self.export_file:
            return

        export_list = []
        for r in self.results.values():
            export_list.append({
                "city": r.city,
                "host": r.host,
                "port": r.port,
                "download_mbps": r.download_mbps,
                "upload_mbps": r.upload_mbps,
                "ping_ms": r.ping_ms,
                "status": r.status,
                "is_fallback": r.is_fallback
            })

        try:
            if self.export_file.endswith(".csv"):
                import csv
                with open(self.export_file, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=export_list[0].keys())
                    writer.writeheader()
                    writer.writerows(export_list)
            else:
                with open(self.export_file, "w", encoding="utf-8") as f:
                    json.dump(export_list, f, indent=2, ensure_ascii=False)
            self.console.print(f"[bold green]✔ Результаты сохранены в:[/] {self.export_file}")
        except Exception as e:
            self.console.print(f"[bold red]✖ Ошибка сохранения файла:[/] {e}")

    def run(self) -> None:
        if not self.check_iperf3_installed():
            self.console.print(Panel(
                "[bold red]Ошибка:[/] Утилита [bold cyan]iperf3[/] не найдена в системе.\n"
                "Убедитесь, что iperf3 установлен и добавлен в системный PATH (или находится рядом со скриптом).",
                title="[bold red]iperf3 не найден[/]",
                border_style="red"
            ))
            return

        if self.json_output:
            # Silent execution for raw JSON output
            for city in self.cities:
                host = SERVERS[city]
                success = self.test_single_server(city, host, is_fallback=False)
                if not success and city in FALLBACK_SERVERS:
                    fb_host = FALLBACK_SERVERS[city]
                    fb_city = FALLBACK_CITIES[city]
                    self.results[city].city = fb_city
                    success = self.test_single_server(city, fb_host, is_fallback=True)
                if not success:
                    self.results[city].status = "OFFLINE"
                time.sleep(INTER_TEST_DELAY)

            raw_res = [
                {
                    "city": r.city,
                    "host": r.host,
                    "download_mbps": r.download_mbps,
                    "upload_mbps": r.upload_mbps,
                    "ping_ms": r.ping_ms,
                    "status": r.status
                }
                for r in self.results.values()
            ]
            print(json.dumps(raw_res, indent=2, ensure_ascii=False))
            return

        start_time = time.time()
        current_status_msg = "Инициализация..."

        def make_layout() -> Layout:
            layout = Layout()
            layout.split_column(
                Layout(name="header", size=5),
                Layout(name="table", size=len(self.cities) + 4),
                Layout(name="footer", size=3)
            )
            layout["header"].update(self.render_header())
            layout["table"].update(self.generate_table(current_status_msg))
            layout["footer"].update(Panel(
                f"[bold cyan]⏳ [bold white]{current_status_msg}[/][/]",
                border_style="cyan",
                box=box.ROUNDED
            ))
            return layout

        with Live(make_layout(), console=self.console, refresh_per_second=8, transient=True) as live:
            for city in self.cities:
                host = SERVERS[city]
                
                def update_cb(msg: str):
                    nonlocal current_status_msg
                    current_status_msg = f"[{city}] {msg}"
                    live.update(make_layout())

                success = self.test_single_server(city, host, is_fallback=False, progress_cb=update_cb)

                if not success and city in FALLBACK_SERVERS:
                    fb_host = FALLBACK_SERVERS[city]
                    fb_city = FALLBACK_CITIES[city]
                    self.results[city].city = fb_city
                    update_cb(f"Основной сервер недоступен. Переключение на {fb_city} ({fb_host})...")
                    success = self.test_single_server(city, fb_host, is_fallback=True, progress_cb=update_cb)

                if not success:
                    self.results[city].status = "OFFLINE"

                update_cb("Завершено")
                time.sleep(INTER_TEST_DELAY)

            current_status_msg = "Все тесты выполнены."
            live.update(make_layout())

        elapsed = time.time() - start_time
        
        # Print final clean view
        self.console.print(self.render_header())
        self.console.print(self.generate_table())
        self.console.print(self.render_summary(elapsed))

        if self.export_file:
            self.export_data()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="⚡ Russian iPerf3 SpeedTest CLI / TUI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Примеры использования:\n"
               "  python speedtest.py                # Запуск полного теста\n"
               "  python speedtest.py -f             # Быстрый тест (по 2 сек)\n"
               "  python speedtest.py -c Moscow      # Тест только Москвы\n"
               "  python speedtest.py --export res.json # Экспорт в JSON"
    )
    parser.add_argument("-d", "--debug", action="store_true", help="Включить подробный вывод отладки")
    parser.add_argument("-f", "--fast", action="store_true", help="Быстрый режим тестирования (2 сек вместо 10)")
    parser.add_argument("-t", "--duration", type=int, default=DEFAULT_TEST_DURATION, help="Длительность одного теста в секундах")
    parser.add_argument("-P", "--streams", type=int, default=DEFAULT_PARALLEL_STREAMS, help="Количество параллельных потоков iperf3")
    parser.add_argument("-c", "--city", nargs="+", choices=CITY_ORDER, help="Выбрать один или несколько городов для теста")
    parser.add_argument("-e", "--export", type=str, help="Путь для сохранения результатов (.json или .csv)")
    parser.add_argument("--json", action="store_true", help="Вывести только сырой JSON в stdout (для интеграций)")

    args = parser.parse_args()

    app = SpeedTester(
        duration=args.duration,
        streams=args.streams,
        debug=args.debug,
        fast_mode=args.fast,
        selected_cities=args.city,
        export_file=args.export,
        json_output=args.json
    )
    try:
        app.run()
    except Exception as e:
        print(f"\n[!] Ошибка при выполнении: {e}")
    finally:
        # If running on Windows directly (e.g. double clicked in Explorer without CLI flags)
        if sys.platform.startswith("win") and len(sys.argv) == 1 and not args.json:
            try:
                input("\nНажмите Enter, чтобы закрыть окно...")
            except (KeyboardInterrupt, EOFError):
                pass


if __name__ == "__main__":
    main()


