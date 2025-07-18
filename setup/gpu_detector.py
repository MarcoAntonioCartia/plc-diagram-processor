"""
GPU Detection and CUDA Version Detection for PLC Diagram Processor
Automatically detects GPU capabilities and determines optimal PyTorch installation
"""

import subprocess
import sys
import os
import platform
import json
from pathlib import Path
from typing import Dict, Optional, Tuple, List

class GPUDetector:
    """Detects GPU capabilities and CUDA version for optimal PyTorch installation"""
    
    def __init__(self):
        self.system_info = {
            "platform": platform.system(),
            "architecture": platform.architecture()[0],
            "python_version": sys.version_info[:2]
        }
        self.gpu_info = None
        self.cuda_info = None
    
    def detect_gpu_capabilities(self) -> Dict:
        """
        Comprehensive GPU detection with multiple fallback methods
        
        Returns:
            Dictionary containing GPU and CUDA information
        """
        print("Detecting GPU capabilities...")
        
        gpu_info = {
            "has_nvidia_gpu": False,
            "has_cuda": False,
            "cuda_version": None,
            "gpu_models": [],
            "gpu_memory": [],
            "compute_capabilities": [],
            "recommended_pytorch": "cpu",
            "pytorch_index_url": "https://download.pytorch.org/whl/cpu"
        }
        
        # Method 1: Try nvidia-ml-py (most reliable)
        nvidia_ml_info = self._detect_with_nvidia_ml()
        if nvidia_ml_info:
            gpu_info.update(nvidia_ml_info)
            print(f"V NVIDIA GPU detected via nvidia-ml-py")
        
        # Method 2: Try nvidia-smi (fallback)
        if not gpu_info["has_nvidia_gpu"]:
            nvidia_smi_info = self._detect_with_nvidia_smi()
            if nvidia_smi_info:
                gpu_info.update(nvidia_smi_info)
                print(f"V NVIDIA GPU detected via nvidia-smi")
        
        # Method 3: Check CUDA installation
        if gpu_info["has_nvidia_gpu"]:
            cuda_info = self._detect_cuda_version()
            if cuda_info:
                gpu_info.update(cuda_info)
                gpu_info["recommended_pytorch"] = self._determine_pytorch_version(cuda_info["cuda_version"])
                gpu_info["pytorch_index_url"] = self._get_pytorch_index_url(cuda_info["cuda_version"])
        
        # Method 4: Check for other GPU types (AMD, Intel)
        other_gpu_info = self._detect_other_gpus()
        if other_gpu_info:
            gpu_info.update(other_gpu_info)
        
        self.gpu_info = gpu_info
        self._print_detection_summary()
        
        return gpu_info
    
    def _detect_with_nvidia_ml(self) -> Optional[Dict]:
        """Detect GPU using nvidia-ml-py library"""
        try:
            import pynvml
            pynvml.nvmlInit()
            
            device_count = pynvml.nvmlDeviceGetCount()
            gpu_models = []
            gpu_memory = []
            compute_capabilities = []
            
            for i in range(device_count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(i)
                
                # Get GPU name (bytes on old pynvml, str on new)
                raw_name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(raw_name, bytes):
                    name = raw_name.decode('utf-8', errors='ignore')
                else:
                    name = str(raw_name)
                gpu_models.append(name)
                
                # Get memory info
                mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                gpu_memory.append(mem_info.total // (1024**3))  # Convert to GB
                
                # Get compute capability
                try:
                    major, minor = pynvml.nvmlDeviceGetCudaComputeCapability(handle)
                    compute_capabilities.append(f"{major}.{minor}")
                except:
                    compute_capabilities.append("Unknown")
            
            pynvml.nvmlShutdown()
            
            return {
                "has_nvidia_gpu": True,
                "gpu_models": gpu_models,
                "gpu_memory": gpu_memory,
                "compute_capabilities": compute_capabilities,
                "detection_method": "nvidia-ml-py"
            }
            
        except ImportError:
            # nvidia-ml-py not installed, try to install it
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "nvidia-ml-py"], 
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return self._detect_with_nvidia_ml()  # Retry after installation
            except:
                pass
        except Exception as e:
            print(f"! nvidia-ml-py detection failed: {e}")
        
        return None
    
    def _detect_with_nvidia_smi(self) -> Optional[Dict]:
        """Detect GPU using nvidia-smi command"""
        try:
            # Try nvidia-smi command
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total,compute_cap", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10
            )
            
            if result.returncode == 0:
                lines = result.stdout.strip().split('\n')
                gpu_models = []
                gpu_memory = []
                compute_capabilities = []
                
                for line in lines:
                    if line.strip():
                        parts = [p.strip() for p in line.split(',')]
                        if len(parts) >= 3:
                            gpu_models.append(parts[0])
                            try:
                                gpu_memory.append(int(float(parts[1]) / 1024))  # Convert MB to GB
                            except:
                                gpu_memory.append(0)
                            compute_capabilities.append(parts[2])
                
                return {
                    "has_nvidia_gpu": True,
                    "gpu_models": gpu_models,
                    "gpu_memory": gpu_memory,
                    "compute_capabilities": compute_capabilities,
                    "detection_method": "nvidia-smi"
                }
        
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
            pass
        except Exception as e:
            print(f"! nvidia-smi detection failed: {e}")
        
        return None
    
    def _detect_cuda_version(self) -> Optional[Dict]:
        """Detect CUDA version from multiple sources"""
        cuda_version = None
        cuda_path = None
        
        # Method 1: nvcc --version
        try:
            result = subprocess.run(["nvcc", "--version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'release' in line.lower():
                        # Extract version like "release 12.1, V12.1.105"
                        import re
                        match = re.search(r'release (\d+\.\d+)', line)
                        if match:
                            cuda_version = match.group(1)
                            break
        except:
            pass
        
        # Method 2: Check CUDA_PATH environment variable
        if not cuda_version:
            cuda_path = os.environ.get('CUDA_PATH') or os.environ.get('CUDA_HOME')
            if cuda_path and os.path.exists(cuda_path):
                # Try to extract version from path
                import re
                match = re.search(r'v(\d+\.\d+)', cuda_path)
                if match:
                    cuda_version = match.group(1)
        
        # Method 3: Try to parse CUDA version from nvidia-smi output (works even
        # when no standalone CUDA toolkit is installed and only the driver is
        # present – common on clean Windows boxes).
        if not cuda_version:
            try:
                smi_res = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=5)
                if smi_res.returncode == 0:
                    import re
                    match = re.search(r"CUDA Version[: ]+([0-9]+\.[0-9]+)", smi_res.stdout)
                    if match:
                        cuda_version = match.group(1)
            except Exception:
                pass  # silent – best-effort only
        
        # Method 4: Check common CUDA installation paths on Windows
        # (this is executed *after* nvidia-smi so that the standalone toolkit,
        # if installed, takes precedence and we can also capture its path).
        # ------------------------------------------------------------------
        
        if cuda_version:
            return {
                "has_cuda": True,
                "cuda_version": cuda_version,
                "cuda_path": cuda_path
            }
        
        # If CUDA version is still unknown but an NVIDIA GPU exists we return
        # a sentinel so that higher-level code can still pick a reasonable GPU
        # wheel (e.g. cu121).  This avoids the misleading "! CUDA not
        # detected" message that confused users.
        if getattr(self, "gpu_info", None) and self.gpu_info.get("has_nvidia_gpu"):
            return {
                "has_cuda": False,
                "cuda_version": None,
                "cuda_path": None,
            }
        
        return None
    
    def _detect_other_gpus(self) -> Optional[Dict]:
        """Detect AMD and Intel GPUs"""
        other_gpus = []
        
        if self.system_info["platform"] == "Windows":
            try:
                # Use wmic to detect GPUs
                result = subprocess.run(
                    ["wmic", "path", "win32_VideoController", "get", "name"],
                    capture_output=True, text=True, timeout=10
                )
                
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')[1:]  # Skip header
                    for line in lines:
                        gpu_name = line.strip()
                        if gpu_name and not gpu_name.lower().startswith('name'):
                            if any(vendor in gpu_name.lower() for vendor in ['amd', 'radeon', 'intel']):
                                other_gpus.append(gpu_name)
            except:
                pass
        
        if other_gpus:
            return {"other_gpus": other_gpus}
        
        return None
    
    def _determine_pytorch_version(self, cuda_version: str) -> str:
        """Determine the best PyTorch version for the detected CUDA version"""
        try:
            # Handle CUDA version strings like "12.8", "12.1", "11.8", etc.
            version_parts = cuda_version.split('.')
            major = int(version_parts[0])
            minor = int(version_parts[1]) if len(version_parts) > 1 else 0
            
            # Enhanced CUDA version mapping for PyTorch
            if major == 12:
                if minor >= 8:  # CUDA 12.8+
                    return "cu128"
                elif minor >= 1:  # CUDA 12.1-12.7
                    return "cu121"
                else:  # CUDA 12.0
                    return "cu121"
            elif major == 11:
                if minor >= 8:  # CUDA 11.8+
                    return "cu118"
                elif minor >= 7:  # CUDA 11.7
                    return "cu117"
                else:  # CUDA 11.0-11.6
                    return "cu118"  # Use 11.8 as fallback
            else:
                return "cpu"  # Very old or unsupported CUDA
        except:
            return "cpu"
    
    def _get_pytorch_index_url(self, cuda_version: str) -> str:
        """Get the appropriate PyTorch index URL for the CUDA version"""
        pytorch_version = self._determine_pytorch_version(cuda_version)
        
        if pytorch_version == "cu128":
            return "https://download.pytorch.org/whl/cu128"
        elif pytorch_version == "cu121":
            return "https://download.pytorch.org/whl/cu121"
        elif pytorch_version == "cu118":
            return "https://download.pytorch.org/whl/cu118"
        elif pytorch_version == "cu117":
            return "https://download.pytorch.org/whl/cu117"
        else:
            return "https://download.pytorch.org/whl/cpu"
    
    def _print_detection_summary(self):
        """Print a summary of detected GPU capabilities"""
        if not self.gpu_info:
            return
        
        print("\n" + "="*50)
        print("  GPU Detection Summary")
        print("="*50)
        
        if self.gpu_info["has_nvidia_gpu"]:
            print(f"V NVIDIA GPU(s) detected:")
            for i, (model, memory, compute) in enumerate(zip(
                self.gpu_info["gpu_models"],
                self.gpu_info["gpu_memory"], 
                self.gpu_info["compute_capabilities"]
            )):
                print(f"  GPU {i}: {model} ({memory}GB, Compute {compute})")
            
            if self.gpu_info["has_cuda"]:
                print(f"V CUDA Version: {self.gpu_info['cuda_version']}")
                print(f"V Recommended PyTorch: {self.gpu_info['recommended_pytorch']}")
            else:
                print("! CUDA not detected - will use CPU version")
        else:
            print("ℹ No NVIDIA GPU detected")
            if self.gpu_info.get("other_gpus"):
                print("Other GPUs found:")
                for gpu in self.gpu_info["other_gpus"]:
                    print(f"  - {gpu}")
        
        print(f" PyTorch installation: {self.gpu_info['pytorch_index_url']}")
        print("="*50)
    
    def get_pytorch_install_command(self) -> Tuple[str, List[str]]:
        """
        Get the appropriate PyTorch installation command
        
        Returns:
            Tuple of (description, command_list)
        """
        if not self.gpu_info:
            self.detect_gpu_capabilities()
        
        base_packages = ["torch", "torchvision", "torchaudio"]
        
        if self.gpu_info["has_nvidia_gpu"] and self.gpu_info["has_cuda"]:
            description = f"Installing PyTorch with CUDA {self.gpu_info['cuda_version']} support"
            command = [
                sys.executable, "-m", "pip", "install"
            ] + base_packages + [
                "--index-url", self.gpu_info["pytorch_index_url"]
            ]
        else:
            description = "Installing PyTorch (CPU-only version)"
            command = [
                sys.executable, "-m", "pip", "install"
            ] + base_packages + [
                "--index-url", "https://download.pytorch.org/whl/cpu"
            ]
        
        return description, command
    
    def save_detection_results(self, output_file: Path):
        """Save detection results to JSON file for later use"""
        if self.gpu_info:
            with open(output_file, 'w') as f:
                json.dump({
                    "system_info": self.system_info,
                    "gpu_info": self.gpu_info,
                    "detection_timestamp": str(Path(__file__).stat().st_mtime)
                }, f, indent=2)

def main():
    """Test the GPU detector"""
    detector = GPUDetector()
    gpu_info = detector.detect_gpu_capabilities()
    
    description, command = detector.get_pytorch_install_command()
    print(f"\n{description}")
    print(f"Command: {' '.join(command)}")
    
    # Save results
    output_file = Path(__file__).parent / "gpu_detection_results.json"
    detector.save_detection_results(output_file)
    print(f"\nResults saved to: {output_file}")

if __name__ == "__main__":
    main()
