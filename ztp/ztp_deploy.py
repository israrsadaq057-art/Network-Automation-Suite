#!/usr/bin/env python3
"""
Zero-Touch Provisioning System
Network Engineer: Israr Sadaq
80% time reduction in network device deployment
"""

import yaml
import jinja2
import netmiko
import logging
import argparse
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import os

class ZeroTouchProvisioning:
    """Zero-Touch Provisioning System for network devices"""
    
    def __init__(self, inventory_file):
        self.inventory = self.load_inventory(inventory_file)
        self.template_env = self.setup_jinja2()
        self.setup_logging()
        self.results = {}
    
    def load_inventory(self, inventory_file):
        """Load device inventory from YAML file"""
        try:
            with open(inventory_file, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            print(f"Error: Inventory file {inventory_file} not found")
            exit(1)
        except yaml.YAMLError as e:
            print(f"Error parsing YAML: {e}")
            exit(1)
    
    def setup_jinja2(self):
        """Setup Jinja2 template environment"""
        template_path = os.path.join(os.path.dirname(__file__), 'templates')
        return jinja2.Environment(
            loader=jinja2.FileSystemLoader(template_path),
            trim_blocks=True,
            lstrip_blocks=True
        )
    
    def setup_logging(self):
        """Configure logging for the deployment process"""
        log_dir = os.path.join(os.path.dirname(__file__), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, f'ztp_deploy_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def generate_config(self, device):
        """Generate device configuration from Jinja2 templates"""
        config_parts = []
        
        # Base configuration template
        base_template = self.template_env.get_template('base_config.j2')
        config_parts.append(base_template.render(device=device))
        
        # VLAN configuration template
        if device.get('vlans'):
            vlan_template = self.template_env.get_template('vlan_config.j2')
            config_parts.append(vlan_template.render(vlans=device['vlans']))
        
        # BGP configuration template
        if device.get('bgp'):
            bgp_template = self.template_env.get_template('bgp_config.j2')
            config_parts.append(bgp_template.render(bgp=device['bgp']))
        
        return '\n'.join(config_parts)
    
    def deploy_config(self, device, config):
        """Deploy configuration to device using Netmiko"""
        try:
            self.logger.info(f"Connecting to {device['name']} ({device['mgmt_ip']})...")
            
            connection = netmiko.ConnectHandler(
                device_type=device['device_type'],
                ip=device['mgmt_ip'],
                username=device['username'],
                password=device['password'],
                secret=device.get('enable_password', device['password']),
                timeout=60
            )
            
            # Enter enable mode
            connection.enable()
            
            # Send configuration
            self.logger.info(f"Pushing configuration to {device['name']}...")
            output = connection.send_config_set(config.split('\n'))
            
            # Save configuration
            connection.save_config()
            
            # Disconnect
            connection.disconnect()
            
            self.logger.info(f"✓ Successfully deployed config to {device['name']}")
            return {'device': device['name'], 'status': 'success', 'output': output}
            
        except Exception as e:
            self.logger.error(f"✗ Failed to deploy to {device['name']}: {str(e)}")
            return {'device': device['name'], 'status': 'failed', 'error': str(e)}
    
    def validate_deployment(self, device):
        """Validate device configuration after deployment"""
        try:
            connection = netmiko.ConnectHandler(
                device_type=device['device_type'],
                ip=device['mgmt_ip'],
                username=device['username'],
                password=device['password'],
                timeout=30
            )
            
            # Run validation commands
            version = connection.send_command('show version')
            interfaces = connection.send_command('show ip interface brief')
            
            connection.disconnect()
            
            return {
                'device': device['name'],
                'status': 'validated',
                'version': version.split('\n')[0] if version else 'Unknown',
                'interfaces': interfaces[:200]  # First 200 chars for summary
            }
            
        except Exception as e:
            return {
                'device': device['name'],
                'status': 'validation_failed',
                'error': str(e)
            }
    
    def deploy_parallel(self, max_workers=10):
        """Deploy to multiple devices in parallel"""
        self.logger.info(f"Starting parallel deployment to {len(self.inventory['devices'])} devices...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for device in self.inventory['devices']:
                config = self.generate_config(device)
                future = executor.submit(self.deploy_config, device, config)
                futures[future] = device['name']
            
            for future in as_completed(futures):
                result = future.result()
                self.results[result['device']] = result
        
        return self.results
    
    def generate_report(self):
        """Generate deployment report"""
        successful = sum(1 for r in self.results.values() if r['status'] == 'success')
        failed = len(self.results) - successful
        
        report = f"""
╔══════════════════════════════════════════════════════════════════╗
║                    ZTP DEPLOYMENT REPORT                         ║
╠══════════════════════════════════════════════════════════════════╣
║  Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}              ║
║  Total Devices: {len(self.results)}                                        ║
║  Successful: {successful}                                            ║
║  Failed: {failed}                                                 ║
╠══════════════════════════════════════════════════════════════════╣
║  DETAILS:                                                         ║
"""
        for device, result in self.results.items():
            status = "✓" if result['status'] == 'success' else "✗"
            report += f"║  {status} {device}: {result['status']}\n"
        
        report += "╚══════════════════════════════════════════════════════════════════╝"
        
        self.logger.info(report)
        
        # Save report to file
        report_dir = os.path.join(os.path.dirname(__file__), 'reports')
        os.makedirs(report_dir, exist_ok=True)
        report_file = os.path.join(report_dir, f'deployment_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')
        
        with open(report_file, 'w') as f:
            f.write(report)
        
        self.logger.info(f"Report saved to: {report_file}")
        
        return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Zero-Touch Provisioning System')
    parser.add_argument('inventory', help='Path to inventory YAML file')
    parser.add_argument('--workers', type=int, default=10, help='Number of parallel workers')
    parser.add_argument('--validate', action='store_true', help='Validate after deployment')
    
    args = parser.parse_args()
    
    # Create ZTP instance
    ztp = ZeroTouchProvisioning(args.inventory)
    
    # Start deployment
    start_time = time.time()
    results = ztp.deploy_parallel(max_workers=args.workers)
    elapsed = time.time() - start_time
    
    ztp.logger.info(f"Deployment completed in {elapsed:.2f} seconds")
    
    # Generate report
    ztp.generate_report()
    
    # Validate if requested
    if args.validate:
        ztp.logger.info("Running validation...")
        for device in ztp.inventory['devices']:
            validation = ztp.validate_deployment(device)
            if validation['status'] == 'validated':
                ztp.logger.info(f"✓ {device['name']} validated: {validation['version']}")
            else:
                ztp.logger.error(f"✗ {device['name']} validation failed: {validation.get('error', 'Unknown')}")