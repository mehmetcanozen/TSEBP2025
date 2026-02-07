"""
Simple Test/Demo Script - Semantic Noise Suppression

Quick test to verify the system is working correctly.
"""

import logging
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from desktop.src.audio.semantic_suppressor import SemanticSuppressor
from desktop.src.profiles.profile_manager import ProfileManager
from desktop.src.profiles.control_engine import ControlEngine, ControlMode

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_semantic_suppressor():
    """Test semantic suppressor with synthetic audio."""
    logger.info("=== Testing Semantic Suppressor ===")
    
    # Create synthetic noisy audio (white noise + sine wave)
    sample_rate = 44100
    duration = 3.0  # seconds
    samples = int(sample_rate * duration)
    
    # Generate test audio
    t = np.linspace(0, duration, samples)
    signal = 0.5 * np.sin(2 * np.pi * 440 * t)  # 440 Hz sine wave (A4)
    noise = 0.1 * np.random.randn(samples)
    noisy_audio = (signal + noise).astype(np.float32)
    
    logger.info(f"Created test audio: {samples} samples @ {sample_rate} Hz")
    
    # Initialize suppressor
    try:
        suppressor = SemanticSuppressor()
        logger.info("✅ SemanticSuppressor initialized")
    except Exception as e:
        logger.error(f"❌ Failed to initialize suppressor: {e}")
        return False
    
    # Test detection
    try:
        detections = suppressor.detect_categories(noisy_audio, sample_rate, threshold=0.3)
        logger.info(f"Detections: {detections}")
    except Exception as e:
        logger.error(f"❌ Detection failed: {e}")
        return False
    
    # Test suppression (no actual suppression, just testing pipeline)
    try:
        clean_audio = suppressor.suppress(
            audio=noisy_audio,
            sample_rate=sample_rate,
            suppress_categories=[],  # Empty for now
        )
        logger.info(f"✅ Suppression pipeline works (output shape: {clean_audio.shape})")
    except Exception as e:
        logger.error(f"❌ Suppression failed: {e}")
        return False
    
    return True


def test_profile_system():
    """Test profile management."""
    logger.info("\n=== Testing Profile System ===")
    
    try:
        manager = ProfileManager()
        logger.info(f"✅ ProfileManager initialized")
        
        profiles = manager.get_all_profiles()
        logger.info(f"Found {len(profiles)} profiles:")
        for p in profiles:
            logger.info(f"  - {p.name} (System: {p.is_system_profile})")
        
        # Test profile creation
        test_profile = manager.create_profile(
            name="Test Profile",
            description="Temporary test profile",
            suppressions={"typing": True, "wind": True}
        )
        logger.info(f"✅ Created test profile: {test_profile.id}")
        
        # Clean up
        manager.delete_profile(test_profile.id)
        logger.info("✅ Deleted test profile")
        
    except Exception as e:
        logger.error(f"❌ Profile system test failed: {e}")
        return False
    
    return True


def test_control_engine():
    """Test control engine."""
    logger.info("\n=== Testing Control Engine ===")
    
    try:
        engine = ControlEngine()
        logger.info("✅ ControlEngine initialized")
        
        # Test mode switching
        engine.set_mode(ControlMode.AUTO)
        logger.info(f"✅ Set mode to: {engine.mode.value}")
        
        # Test profile switching
        engine.set_profile_by_id("default-focus")
        logger.info(f"✅ Set profile to: {engine.current_profile.name}")
        
        # Get status
        status = engine.get_status()
        logger.info(f"Engine status: {status}")
        
    except Exception as e:
        logger.error(f"❌ Control engine test failed: {e}")
        return False
    
    return True


def main():
    """Run all tests."""
    logger.info("🚀 Semantic Noise Suppression - System Test\n")
    
    results = []
    
    # Test 1: Semantic Suppressor
    results.append(("Semantic Suppressor", test_semantic_suppressor()))
    
    # Test 2: Profile System
    results.append(("Profile System", test_profile_system()))
    
    # Test 3: Control Engine
    results.append(("Control Engine", test_control_engine()))
    
    # Summary
    logger.info("\n" + "="*50)
    logger.info("TEST SUMMARY")
    logger.info("="*50)
    
    all_passed = True
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{name}: {status}")
        all_passed = all_passed and passed
    
    logger.info("="*50)
    
    if all_passed:
        logger.info("\n🎉 All tests passed!")
        return 0
    else:
        logger.error("\n⚠️ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
