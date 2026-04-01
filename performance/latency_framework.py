#!/usr/bin/env python3
"""
Network Performance Testing Framework
Network Engineer: Israr Sadaq
Automated Latency, Jitter, Throughput, and Packet Loss Measurement

Features:
- Automated iPerf3 tests between network endpoints
- Real-time latency and jitter monitoring
- Throughput testing up to 10Gbps
- Packet loss detection
- Performance report generation
- Prometheus metrics export
"""

import iperf3
import time
import json
import logging
import argparse
import threading
import queue
import csv
from datetime import datetime
from pathlib import Path
import statistics
import requests
import signal
import sys

class PerformanceMonitor:
    """Automated network performance monitoring system"""
    
    def __init__(self, config_file=None):
        self.config = self.load_config(config_file) if config_file else self.default_config()
        self.setup_logging()
        self.results = []
        self.running = True
        self.test_queue = queue.Queue()
        self.setup_signal_handlers()
        
    def default_config(self):
        """Default configuration"""
        return {
            "test_duration": 10,
            "num_streams": 4,
            "interval_seconds": 60,
            "thresholds": {
                "latency_ms": 50,
                "jitter_ms": 10,
                "packet_loss_percent": 1,
                "throughput_mbps": 100
            },
            "test_points": [
                {"name": "Berlin-DC", "ip": "10.10.10.10", "role": "server"},
                {"name": "Frankfurt-DC", "ip": "10.10.10.20", "role": "client"},
                {"name": "Munich-PoP", "ip": "10.10.10.30", "role": "client"},
                {"name": "Hamburg-PoP", "ip": "10.10.10.40", "role": "client"}
            ],
            "test_paths": [
                {"source": "Berlin-DC", "destination": "Frankfurt-DC"},
                {"source": "Berlin-DC", "destination": "Munich-PoP"},
                {"source": "Berlin-DC", "destination": "Hamburg-PoP"},
                {"source": "Frankfurt-DC", "destination": "Munich-PoP"}
            ]
        }
    
    def load_config(self, config_file):
        """Load configuration from JSON file"""
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            self.logger.warning(f"Config file {config_file} not found, using defaults")
            return self.default_config()
    
    def setup_logging(self):
        """Configure logging for the performance monitor"""
        log_dir = Path(__file__).parent / "logs"
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / f"performance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_signal_handlers(self):
        """Handle Ctrl+C gracefully"""
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, sig, frame):
        """Signal handler for graceful shutdown"""
        self.logger.info("Shutting down performance monitor...")
        self.running = False
    
    def get_device_info(self, device_name):
        """Get device details by name"""
        for device in self.config["test_points"]:
            if device["name"] == device_name:
                return device
        return None
    
    def run_iperf_test(self, source, destination, role="client"):
        """
        Run iPerf3 test between source and destination
        
        Args:
            source: Source device name
            destination: Destination device name or IP
            role: 'client' or 'server'
        
        Returns:
            Dictionary with test results or None if failed
        """
        source_device = self.get_device_info(source)
        dest_device = self.get_device_info(destination) if isinstance(destination, str) else None
        dest_ip = dest_device["ip"] if dest_device else destination
        
        try:
            client = iperf3.Client()
            client.server_hostname = dest_ip
            client.port = 5201
            client.duration = self.config["test_duration"]
            client.num_streams = self.config["num_streams"]
            client.protocol = 'tcp'
            client.reverse = True  # Measure both directions
            
            self.logger.info(f"Running test: {source} -> {dest_ip} (duration: {client.duration}s)")
            
            result = client.run()
            
            if result.error:
                self.logger.error(f"iPerf test failed: {result.error}")
                return None
            
            metrics = {
                'timestamp': datetime.utcnow().isoformat(),
                'source': source,
                'destination': dest_ip,
                'destination_name': dest_device["name"] if dest_device else destination,
                'latency_avg_ms': result.latency_avg_ms,
                'latency_min_ms': result.latency_min_ms,
                'latency_max_ms': result.latency_max_ms,
                'jitter_ms': result.jitter_ms,
                'throughput_mbps': result.received_Mbps,
                'packet_loss_percent': result.lost_percent,
                'retransmits': result.retransmits,
                'bytes_transferred': result.bytes,
                'test_duration': result.duration,
                'num_streams': self.config["num_streams"]
            }
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Exception during iPerf test: {e}")
            return None
    
    def run_all_tests(self):
        """Run all configured test paths"""
        results = []
        
        for test_path in self.config["test_paths"]:
            source = test_path["source"]
            destination = test_path["destination"]
            
            self.logger.info(f"Testing path: {source} -> {destination}")
            result = self.run_iperf_test(source, destination)
            
            if result:
                results.append(result)
                self.logger.info(f"✓ {source} -> {destination}: "
                               f"Latency: {result['latency_avg_ms']:.2f}ms, "
                               f"Jitter: {result['jitter_ms']:.2f}ms, "
                               f"Throughput: {result['throughput_mbps']:.2f}Mbps")
                
                # Check thresholds
                self.check_thresholds(result)
            else:
                self.logger.error(f"✗ Test failed: {source} -> {destination}")
            
            time.sleep(2)  # Small delay between tests
        
        return results
    
    def check_thresholds(self, result):
        """Check if results exceed thresholds"""
        thresholds = self.config["thresholds"]
        alerts = []
        
        if result['latency_avg_ms'] > thresholds['latency_ms']:
            alerts.append(f"High latency: {result['latency_avg_ms']:.2f}ms > {thresholds['latency_ms']}ms")
        
        if result['jitter_ms'] > thresholds['jitter_ms']:
            alerts.append(f"High jitter: {result['jitter_ms']:.2f}ms > {thresholds['jitter_ms']}ms")
        
        if result['packet_loss_percent'] > thresholds['packet_loss_percent']:
            alerts.append(f"Packet loss: {result['packet_loss_percent']:.2f}% > {thresholds['packet_loss_percent']}%")
        
        if result['throughput_mbps'] < thresholds['throughput_mbps']:
            alerts.append(f"Low throughput: {result['throughput_mbps']:.2f}Mbps < {thresholds['throughput_mbps']}Mbps")
        
        if alerts:
            self.logger.warning(f"ALERTS for {result['source']} -> {result['destination_name']}: {', '.join(alerts)}")
            self.send_alert(result, alerts)
        
        return alerts
    
    def send_alert(self, result, alerts):
        """Send alert to webhook/email"""
        alert_data = {
            "timestamp": result['timestamp'],
            "source": result['source'],
            "destination": result['destination_name'],
            "alerts": alerts,
            "metrics": {
                "latency": result['latency_avg_ms'],
                "jitter": result['jitter_ms'],
                "throughput": result['throughput_mbps'],
                "packet_loss": result['packet_loss_percent']
            }
        }
        
        # Send to Prometheus Pushgateway if configured
        if self.config.get('pushgateway_url'):
            try:
                requests.post(
                    f"{self.config['pushgateway_url']}/metrics/job/performance_monitor",
                    data=self.format_prometheus_metrics(result),
                    timeout=5
                )
            except Exception as e:
                self.logger.error(f"Failed to send to Pushgateway: {e}")
        
        # Log alert
        self.logger.warning(f"Alert sent: {json.dumps(alert_data)}")
    
    def format_prometheus_metrics(self, result):
        """Format results as Prometheus metrics"""
        return f"""
# HELP network_latency_ms Network latency in milliseconds
# TYPE network_latency_ms gauge
network_latency_ms{{source="{result['source']}",dest="{result['destination_name']}"}} {result['latency_avg_ms']}

# HELP network_jitter_ms Network jitter in milliseconds
# TYPE network_jitter_ms gauge
network_jitter_ms{{source="{result['source']}",dest="{result['destination_name']}"}} {result['jitter_ms']}

# HELP network_throughput_mbps Network throughput in Mbps
# TYPE network_throughput_mbps gauge
network_throughput_mbps{{source="{result['source']}",dest="{result['destination_name']}"}} {result['throughput_mbps']}

# HELP packet_loss_percent Packet loss percentage
# TYPE packet_loss_percent gauge
packet_loss_percent{{source="{result['source']}",dest="{result['destination_name']}"}} {result['packet_loss_percent']}
"""
    
    def continuous_monitoring(self):
        """Run tests continuously on schedule"""
        self.logger.info(f"Starting continuous monitoring (interval: {self.config['interval_seconds']}s)")
        
        while self.running:
            try:
                start_time = time.time()
                results = self.run_all_tests()
                self.results.extend(results)
                
                # Generate intermediate report
                self.generate_report(partial=True)
                
                # Calculate wait time
                elapsed = time.time() - start_time
                wait_time = max(0, self.config['interval_seconds'] - elapsed)
                
                if wait_time > 0 and self.running:
                    self.logger.info(f"Next test cycle in {wait_time:.0f} seconds")
                    time.sleep(wait_time)
                    
            except Exception as e:
                self.logger.error(f"Error in monitoring loop: {e}")
                time.sleep(30)
    
    def generate_report(self, partial=False):
        """Generate performance report"""
        if not self.results:
            self.logger.info("No results to report")
            return
        
        report_dir = Path(__file__).parent / "reports"
        report_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_dir / f"performance_report_{timestamp}.json"
        csv_file = report_dir / f"performance_report_{timestamp}.csv"
        
        # Calculate statistics
        latencies = [r['latency_avg_ms'] for r in self.results if r]
        jitters = [r['jitter_ms'] for r in self.results if r]
        throughputs = [r['throughput_mbps'] for r in self.results if r]
        packet_losses = [r['packet_loss_percent'] for r in self.results if r]
        
        report = {
            'timestamp': timestamp,
            'total_tests': len(self.results),
            'statistics': {
                'latency': {
                    'min': min(latencies) if latencies else 0,
                    'max': max(latencies) if latencies else 0,
                    'avg': statistics.mean(latencies) if latencies else 0,
                    'stddev': statistics.stdev(latencies) if len(latencies) > 1 else 0
                },
                'jitter': {
                    'min': min(jitters) if jitters else 0,
                    'max': max(jitters) if jitters else 0,
                    'avg': statistics.mean(jitters) if jitters else 0
                },
                'throughput': {
                    'min': min(throughputs) if throughputs else 0,
                    'max': max(throughputs) if throughputs else 0,
                    'avg': statistics.mean(throughputs) if throughputs else 0
                },
                'packet_loss': {
                    'min': min(packet_losses) if packet_losses else 0,
                    'max': max(packet_losses) if packet_losses else 0,
                    'avg': statistics.mean(packet_losses) if packet_losses else 0
                }
            },
            'test_results': self.results[-50:] if partial else self.results  # Last 50 for partial reports
        }
        
        # Save JSON report
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        # Save CSV report
        with open(csv_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=self.results[0].keys() if self.results else [])
            writer.writeheader()
            writer.writerows(self.results)
        
        self.logger.info(f"Report saved: {report_file}")
        self.logger.info(f"CSV saved: {csv_file}")
        
        # Print summary
        self.print_summary(report)
        
        return report
    
    def print_summary(self, report):
        """Print performance summary"""
        stats = report['statistics']
        
        print("\n" + "="*60)
        print("NETWORK PERFORMANCE SUMMARY")
        print("="*60)
        print(f"Total Tests: {report['total_tests']}")
        print(f"\n📊 Latency (ms):")
        print(f"   Min: {stats['latency']['min']:.2f} | Max: {stats['latency']['max']:.2f} | Avg: {stats['latency']['avg']:.2f}")
        print(f"\n📈 Jitter (ms):")
        print(f"   Min: {stats['jitter']['min']:.2f} | Max: {stats['jitter']['max']:.2f} | Avg: {stats['jitter']['avg']:.2f}")
        print(f"\n⚡ Throughput (Mbps):")
        print(f"   Min: {stats['throughput']['min']:.2f} | Max: {stats['throughput']['max']:.2f} | Avg: {stats['throughput']['avg']:.2f}")
        print(f"\n📉 Packet Loss (%):")
        print(f"   Min: {stats['packet_loss']['min']:.2f} | Max: {stats['packet_loss']['max']:.2f} | Avg: {stats['packet_loss']['avg']:.2f}")
        print("="*60 + "\n")
    
    def run_once(self):
        """Run a single test cycle"""
        self.logger.info("Running single test cycle...")
        results = self.run_all_tests()
        self.results = results
        return self.generate_report()
    
    def run_daemon(self):
        """Run as a daemon with continuous monitoring"""
        self.logger.info("Starting performance monitoring daemon...")
        self.continuous_monitoring()

def main():
    parser = argparse.ArgumentParser(description='Network Performance Testing Framework')
    parser.add_argument('--config', help='Configuration file path')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    parser.add_argument('--daemon', action='store_true', help='Run as continuous daemon')
    parser.add_argument('--duration', type=int, help='Test duration in seconds')
    parser.add_argument('--interval', type=int, help='Test interval in seconds')
    
    args = parser.parse_args()
    
    monitor = PerformanceMonitor(args.config)
    
    # Override config if provided
    if args.duration:
        monitor.config['test_duration'] = args.duration
    if args.interval:
        monitor.config['interval_seconds'] = args.interval
    
    if args.once:
        monitor.run_once()
    elif args.daemon:
        monitor.run_daemon()
    else:
        # Default: run once then continuous
        monitor.run_once()
        monitor.run_daemon()

if __name__ == "__main__":
    main()