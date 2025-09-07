import argparse
import threading
import requests
import time
from urllib.parse import urlparse
import random
import json
from datetime import datetime
import sys
import signal
import ssl
from urllib3.util.ssl_ import create_urllib3_context

# Bypass SSL verification warnings (for testing purposes only)
requests.packages.urllib3.disable_warnings()

class StressEngine:
    def __init__(self):
        self.is_running = False
        self.threads = []
        self.result = {'success': 0, 'fail': 0, 'timeout': 0, 'ssl_error': 0, 'connection_error': 0}
        self.start_time = None
        self.request_timestamps = []
        
    def worker(self, target_url, thread_id, requests_count, user_agents, timeout, use_ssl_verify):
        session = requests.Session()
        
        # Create a custom SSL context that's more permissive
        if not use_ssl_verify:
            session.verify = False
            # Bypass hostname verification
            session.mount('https://', TLSAdapter())
        
        for i in range(requests_count):
            if not self.is_running:
                break
            try:
                headers = {
                    'User-Agent': random.choice(user_agents),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Cache-Control': 'max-age=0',
                    'DNT': '1'
                }
                
                start_time = time.time()
                r = session.get(target_url, headers=headers, timeout=timeout, allow_redirects=True)
                end_time = time.time()
                
                if r.status_code == 200:
                    self.result['success'] += 1
                    self.request_timestamps.append((end_time, 'success', end_time - start_time))
                    if thread_id == 0 and i % 10 == 0:  # Only show some successes to avoid spam
                        print(f"[+] Thread {thread_id}: Request {i+1} successful (Status: {r.status_code}, Time: {end_time - start_time:.2f}s)")
                else:
                    self.result['fail'] += 1
                    self.request_timestamps.append((end_time, 'fail', end_time - start_time))
                    if thread_id == 0 and i % 5 == 0:  # Only show some failures to avoid spam
                        print(f"[-] Thread {thread_id}: Request {i+1} failed (Status: {r.status_code})")
                    
            except requests.exceptions.Timeout:
                self.result['timeout'] += 1
                self.request_timestamps.append((time.time(), 'timeout', 0))
                if thread_id == 0 and i % 10 == 0:
                    print(f"[!] Thread {thread_id}: Request {i+1} timeout")
            except requests.exceptions.SSLError:
                self.result['ssl_error'] += 1
                self.request_timestamps.append((time.time(), 'ssl_error', 0))
                if thread_id == 0 and i % 10 == 0:
                    print(f"[!] Thread {thread_id}: Request {i+1} SSL error")
            except requests.exceptions.ConnectionError:
                self.result['connection_error'] += 1
                self.request_timestamps.append((time.time(), 'connection_error', 0))
                if thread_id == 0 and i % 10 == 0:
                    print(f"[!] Thread {thread_id}: Request {i+1} connection error")
            except Exception as e:
                self.result['fail'] += 1
                self.request_timestamps.append((time.time(), 'error', 0))
                if thread_id == 0 and i % 10 == 0:
                    print(f"[!] Thread {thread_id}: Request {i+1} error: {str(e)}")

    def start_attack(self, target_url, port, thread_count, requests_per_thread, timeout=5, use_ssl_verify=False):
        parsed = urlparse(target_url)
        
        # Ensure proper URL format
        if not parsed.scheme:
            if port == 443:
                target_url = f"https://{target_url}"
            else:
                target_url = f"http://{target_url}:{port}"
        elif parsed.scheme == "https" and port != 443:
            target_url = f"https://{parsed.netloc}:{port}{parsed.path}"
        
        self.is_running = True
        self.result = {'success': 0, 'fail': 0, 'timeout': 0, 'ssl_error': 0, 'connection_error': 0}
        self.threads = []
        self.start_time = time.time()
        self.request_timestamps = []
        
        # More realistic user agents
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36',
            'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1',
            'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)',
            'Mozilla/5.0 (compatible; Bingbot/2.0; +http://www.bing.com/bingbot.htm)'
        ]
        
        print(f"[*] Starting stress test on {target_url}")
        print(f"[*] Using {thread_count} threads with {requests_per_thread} requests each")
        print(f"[*] Total requests: {thread_count * requests_per_thread}")
        print(f"[*] Timeout: {timeout}s, SSL Verify: {use_ssl_verify}")
        print("[*] Press Ctrl+C to stop the attack\n")
        
        for i in range(thread_count):
            t = threading.Thread(
                target=self.worker, 
                args=(target_url, i, requests_per_thread, user_agents, timeout, use_ssl_verify)
            )
            t.daemon = True
            t.start()
            self.threads.append(t)
        
        return target_url

    def stop_attack(self):
        self.is_running = False
        for t in self.threads:
            t.join(timeout=1.0)
        return self.result
    
    def get_stats(self):
        total = sum(self.result.values())
        success_rate = (self.result['success'] / total) * 100 if total > 0 else 0
        
        # Calculate requests per second
        current_time = time.time()
        elapsed = current_time - self.start_time if self.start_time else 0
        rps = total / elapsed if elapsed > 0 else 0
        
        return {
            'success': self.result['success'],
            'fail': self.result['fail'],
            'timeout': self.result['timeout'],
            'ssl_error': self.result['ssl_error'],
            'connection_error': self.result['connection_error'],
            'success_rate': success_rate,
            'total_requests': total,
            'rps': rps,
            'elapsed_time': elapsed
        }

# Custom adapter to handle SSL issues
class TLSAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = ctx
        return super(TLSAdapter, self).init_poolmanager(*args, **kwargs)

def signal_handler(sig, frame):
    print("\n[*] Stopping attack...")
    engine.stop_attack()
    stats = engine.get_stats()
    
    print("\n" + "="*60)
    print("ATTACK SUMMARY")
    print("="*60)
    print(f"Target: {args.url}")
    print(f"Successful requests: {stats['success']}")
    print(f"Failed requests: {stats['fail']}")
    print(f"Timeout errors: {stats['timeout']}")
    print(f"SSL errors: {stats['ssl_error']}")
    print(f"Connection errors: {stats['connection_error']}")
    print(f"Success rate: {stats['success_rate']:.2f}%")
    print(f"Requests per second: {stats['rps']:.2f}")
    print(f"Elapsed time: {stats['elapsed_time']:.2f}s")
    print("="*60)
    
    # Save results to file
    try:
        filename = f"stress_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            result_data = {
                'target': args.url,
                'timestamp': datetime.now().isoformat(),
                'stats': stats
            }
            json.dump(result_data, f, indent=2)
        print(f"[*] Results saved to {filename}")
    except Exception as e:
        print(f"[!] Failed to save results: {e}")
    
    sys.exit(0)

def main():
    global engine, args
    
    parser = argparse.ArgumentParser(description='Advanced Load Tester - Terminal Version')
    parser.add_argument('url', help='Target URL (e.g., https://example.com or example.com)')
    parser.add_argument('-p', '--port', type=int, default=443, help='Target port (default: 443 for HTTPS, 80 for HTTP)')
    parser.add_argument('-t', '--threads', type=int, default=50, help='Number of threads (default: 50)')
    parser.add_argument('-r', '--requests', type=int, default=100, help='Requests per thread (default: 100)')
    parser.add_argument('-T', '--timeout', type=int, default=5, help='Request timeout in seconds (default: 5)')
    parser.add_argument('--no-ssl-verify', action='store_true', help='Disable SSL certificate verification')
    parser.add_argument('--delay', type=float, default=0, help='Delay between requests in seconds (default: 0)')
    
    args = parser.parse_args()
    
    # Auto-detect port based on URL scheme
    parsed_url = urlparse(args.url)
    if not parsed_url.scheme and args.port == 443:
        if args.url.startswith('https://'):
            args.port = 443
        else:
            args.port = 80
    
    # Register signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    engine = StressEngine()
    engine.start_attack(args.url, args.port, args.threads, args.requests, args.timeout, not args.no_ssl_verify)
    
    # Keep the main thread alive and show periodic stats
    try:
        last_stats_time = time.time()
        while engine.is_running:
            time.sleep(1)
            stats = engine.get_stats()
            
            # Show stats every 5 seconds
            if time.time() - last_stats_time >= 5:
                print(f"\n[*] Current stats: {stats['success']} success, {stats['fail']} failed, "
                      f"{stats['timeout']} timeout, {stats['ssl_error']} SSL errors, "
                      f"{stats['connection_error']} connection errors, RPS: {stats['rps']:.2f}")
                last_stats_time = time.time()
            
            # Auto-stop if we've completed all requests
            max_requests = args.threads * args.requests
            if stats['total_requests'] >= max_requests:
                break
                
    except KeyboardInterrupt:
        pass
    
    # Print final stats
    signal_handler(None, None)

if __name__ == '__main__':
    main()
