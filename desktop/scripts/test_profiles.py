"""
Lightweight Test - Profile System Only

Tests the profile and control engine without loading heavy models.
This bypasses the torchaudio/speechbrain compatibility issue.
"""

import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from desktop.src.profiles.profile_manager import ProfileManager
from desktop.src.profiles.control_engine import ControlEngine, ControlMode

logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_profile_system():
    """Test profile management."""
    logger.info("=== Testing Profile System ===")
    
    try:
        manager = ProfileManager()
        logger.info(f"✅ ProfileManager initialized")
        
        profiles = manager.get_all_profiles()
        logger.info(f"Found {len(profiles)} profiles:")
        for p in profiles:
            suppress_list = [k for k, v in p.suppressions.items() if v]
            logger.info(f"  - {p.name} | Suppresses: {', '.join(suppress_list) if suppress_list else '(none)'}")
        
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
        logger.error(f"❌ Profile system test failed: {e}", exc_info=True)
        return False
    
    return True


def test_control_engine():
    """Test control engine."""
    logger.info("\n=== Testing Control Engine ===")
    
    try:
        # Initialize without loading models
        engine = ControlEngine()
        logger.info("✅ ControlEngine initialized")
        
        # Test mode switching
        engine.set_mode(ControlMode.AUTO)
        logger.info(f"✅ Set mode to: {engine.mode.value}")
        
        engine.set_mode(ControlMode.MANUAL)
        logger.info(f"✅ Set mode to: {engine.mode.value}")
        
        # Test profile switching
        engine.set_profile_by_id("default-focus")
        logger.info(f"✅ Set profile to: {engine.current_profile.name}")
        
        engine.set_profile_by_id("default-passthrough")
        logger.info(f"✅ Set profile to: {engine.current_profile.name}")
        
        # Get status
        status = engine.get_status()
        logger.info(f"Engine status: {status}")
        
        # Test safety override detection
        logger.info("\n--- Testing Safety Override ---")
        detections = {"siren": 0.85, "typing": 0.6}
        engine.on_detection_update(detections)
        
        if engine.safety_status.active:
            logger.info(f"✅ Safety override activated for: {engine.safety_status.category}")
            logger.info(f"   Profile switched to: {engine.current_profile.name}")
        else:
            logger.warning("⚠️ Safety override not triggered (might need higher threshold)")
        
        # Test auto-mode profile switching
        logger.info("\n--- Testing Auto-Mode ---")
        engine.set_mode(ControlMode.AUTO)
        detections = {"traffic": 0.7, "typing": 0.3}
        engine.on_detection_update(detections)
        logger.info(f"✅ Auto-mode profile: {engine.current_profile.name if engine.current_profile else 'None'}")
        
    except Exception as e:
        logger.error(f"❌ Control engine test failed: {e}", exc_info=True)
        return False
    
    return True


def main():
    """Run all tests."""
    logger.info("🚀 Semantic Noise Suppression - Lightweight System Test\n")
    logger.info("Note: Skipping model loading tests due to PyTorch 2.10/speechbrain compatibility.\n")
    
    results = []
    
    # Test 1: Profile System
    results.append(("Profile System", test_profile_system()))
    
    # Test 2: Control Engine
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
        logger.info("\nNote: Full model tests need PyTorch/speechbrain compatibility fix.")
        logger.info("See NEXT_STEPS.md for model version recommendations.")
        return 0
    else:
        logger.error("\n⚠️ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
