#!/usr/bin/env python3
"""
Log Processing Pipeline Controller
Runs processing steps continuously as fast as possible
"""
import subprocess
import signal
import sys
import threading
from pathlib import Path
from datetime import datetime
import time

class LogPipeline:
    def __init__(self):
        self.should_run = True
        self.processing_lock = threading.Lock()
        self.is_processing = False
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)
    
    def shutdown(self, *_):
        print("\n[PIPELINE] Shutting down...")
        self.should_run = False
        sys.exit(0)
    
    def check_prerequisites(self):
        """Ensure all required scripts exist"""
        required = ['clean.py', 'batchgrper.py', 'batchmanager.py']
        missing = [f for f in required if not Path(f).exists()]
        if missing:
            print(f"[ERROR] Missing files: {', '.join(missing)}")
            return False
        
        # Check if logs.db exists (means raw_logs.py has run)
        if not Path('logs.db').exists():
            print("[WARNING] logs.db not found - make sure raw_logs.py is running!")
            print("         Start it with: python3 raw_logs.py &")
            return False
        
        return True
    
    def run_step(self, script, description):
        """Run a processing step and check for errors"""
        result = subprocess.run(
            ['python3', script],
            capture_output=True,
            text=True
        )
        
        status = "✓" if result.returncode == 0 else "✗"
        timestamp = datetime.now().strftime('%H:%M:%S')
        
        return {
            'script': script,
            'description': description,
            'status': status,
            'success': result.returncode == 0,
            'output': result.stdout.strip() if result.stdout else '',
            'error': result.stderr.strip() if result.stderr else '',
            'timestamp': timestamp
        }
    
    def process_cycle_continuous(self, cycle_num):
        """Run one complete processing cycle"""
        print(f"\n[CYCLE {cycle_num}] {datetime.now().strftime('%H:%M:%S')}")
        
        steps = [
            ('clean.py', 'Extract templates', False),
            ('batchgrper.py', 'Group by component', False),
            ('batchmanager.py', 'Analyze batches', True)  # Show full output
        ]
        
        for script, desc, show_full in steps:
            result = self.run_step(script, desc)
            print(f"  {result['status']} {result['description']}", end='')
            
            # Show output
            if result['success'] and result['output']:
                if show_full:
                    # Show all output for batchmanager
                    print()
                    for line in result['output'].split('\n'):
                        if line.strip():
                            print(f"    {line}")
                else:
                    # Show just first meaningful line for others
                    lines = result['output'].split('\n')
                    for line in lines:
                        if line and not line.startswith('[') and not line.startswith('='):
                            print(f" → {line.strip()}")
                            break
                    else:
                        print()
            else:
                print()
            
            if not result['success']:
                print(f"    ERROR: {result['error']}")
    
    def run_live(self):
        """Run processing continuously in a tight loop"""
        print("=" * 60)
        print("LOG PROCESSING PIPELINE (LIVE MODE)")
        print("=" * 60)
        print("\nNOTE: Make sure raw_logs.py is running in the background!")
        print("      If not started: python3 raw_logs.py &\n")
        print("[PIPELINE] Running continuously with smart delay")
        print("[PIPELINE] Press Ctrl+C to stop\n")
        
        if not self.check_prerequisites():
            return
        
        cycle = 1
        try:
            while self.should_run:
                self.process_cycle_continuous(cycle)
                cycle += 1
                # Short delay to avoid DB locks and CPU thrashing
                # SQLite needs brief moments to release locks
                time.sleep(2)
        
        except KeyboardInterrupt:
            self.shutdown()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Log Processing Pipeline - Live continuous processing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # First, start the log collector in background:
  python3 raw_logs.py &
  
  # Then run the pipeline in LIVE mode (processes as fast as possible)
  python3 log_pipeline.py
  
  # Or with custom delay between cycles (in seconds)
  python3 log_pipeline.py --interval 10
        """
    )
    parser.add_argument('--interval', type=float, default=0.1,
                       help='Seconds between cycles (default: 0.1 for near-instant)')
    
    args = parser.parse_args()
    
    pipeline = LogPipeline()
    
    if args.interval == 0.1:
        # Live mode - as fast as possible
        pipeline.run_live()
    else:
        # Custom interval mode
        print(f"[PIPELINE] Running with {args.interval}s interval")
        cycle = 1
        try:
            while pipeline.should_run:
                pipeline.process_cycle_continuous(cycle)
                cycle += 1
                time.sleep(args.interval)
        except KeyboardInterrupt:
            pipeline.shutdown()