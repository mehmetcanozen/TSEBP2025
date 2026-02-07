"""
Auto Controller - Automatically select profiles based on detected sounds
"""

from typing import Optional, Tuple, Dict, List
from dataclasses import dataclass
from profile_manager import Profile, ProfileManager


@dataclass
class AutoRecommendation:
    """Auto-mode recommendation"""
    profile: Optional[Profile]
    reason: str
    confidence: float  # 0-1 confidence score


class AutoController:
    """Controls automatic profile selection based on audio detections"""
    
    def __init__(self, profile_manager: ProfileManager):
        """
        Initialize AutoController
        
        Args:
            profile_manager: ProfileManager instance
        """
        self.profile_manager = profile_manager
        self.current_profile: Optional[Profile] = None
        self.last_recommendation: Optional[AutoRecommendation] = None
    
    def evaluate(self, detections: Dict[str, float]) -> Optional[Profile]:
        """
        Evaluate detections and find best matching profile
        
        Args:
            detections: Dictionary of detection categories with confidence scores
                       e.g. {"speech": 0.8, "traffic": 0.6, "wind": 0.1, "typing": 0.4}
        
        Returns:
            Best matching Profile, or None if no match found
        """
        best_profile = None
        best_confidence = 0.0
        
        profiles = self.profile_manager.get_all_profiles()
        
        for profile in profiles:
            # Skip profiles without auto triggers
            if not profile.autoTriggers:
                continue
            
            # Check if profile's triggers match detections
            profile_confidence = self._evaluate_profile_triggers(profile, detections)
            
            if profile_confidence > best_confidence:
                best_confidence = profile_confidence
                best_profile = profile
        
        return best_profile
    
    def _evaluate_profile_triggers(self, profile: Profile, detections: Dict[str, float]) -> float:
        """
        Calculate confidence score for a profile based on its triggers
        
        Args:
            profile: Profile to evaluate
            detections: Current detections
        
        Returns:
            Confidence score (0-1)
        """
        if not profile.autoTriggers:
            return 0.0
        
        # Check how many triggers are satisfied
        matched_triggers = 0
        
        for trigger in profile.autoTriggers:
            category = trigger.get('category')
            threshold = trigger.get('threshold', 0.5)
            
            detection_value = detections.get(category, 0.0)
            
            if detection_value >= threshold:
                matched_triggers += 1
        
        # Return confidence as ratio of matched triggers
        if matched_triggers > 0:
            confidence = min(1.0, matched_triggers / len(profile.autoTriggers))
            return confidence
        
        return 0.0
    
    def get_recommendation(self, detections: Dict[str, float]) -> AutoRecommendation:
        """
        Get auto-mode recommendation with explanation
        
        Args:
            detections: Current detection results
        
        Returns:
            AutoRecommendation with profile and reason
        
        Examples:
            - ("Commute Mode", "Detected: Traffic (75%)")
            - ("Office Mode", "Detected: Speech (85%) + Typing (60%)")
        """
        profile = self.evaluate(detections)
        
        if profile is None:
            recommendation = AutoRecommendation(
                profile=None,
                reason="No triggers matched",
                confidence=0.0
            )
        else:
            confidence = self._evaluate_profile_triggers(profile, detections)
            
            # Build reason string
            triggered_categories = []
            for trigger in profile.autoTriggers:
                category = trigger.get('category')
                threshold = trigger.get('threshold', 0.5)
                detection_value = detections.get(category, 0.0)
                
                if detection_value >= threshold:
                    percentage = int(detection_value * 100)
                    triggered_categories.append(f"{category.capitalize()} ({percentage}%)")
            
            reason = f"Detected: {', '.join(triggered_categories)}"
            
            recommendation = AutoRecommendation(
                profile=profile,
                reason=reason,
                confidence=confidence
            )
        
        self.last_recommendation = recommendation
        return recommendation
    
    def should_switch_profile(self, new_profile: Profile, 
                             current_profile: Optional[Profile],
                             hysteresis: float = 0.1) -> bool:
        """
        Determine if we should switch to a new profile
        
        Applies hysteresis to avoid constant switching
        
        Args:
            new_profile: Profile we're considering switching to
            current_profile: Current active profile
            hysteresis: Minimum confidence difference to trigger switch (0-1)
        
        Returns:
            True if should switch, False otherwise
        """
        # Always switch if no current profile
        if current_profile is None:
            return True
        
        # Don't switch to the same profile
        if new_profile.id == current_profile.id:
            return False
        
        # Get confidence of both profiles
        if self.last_recommendation and self.last_recommendation.profile:
            new_confidence = self.last_recommendation.confidence
        else:
            new_confidence = 0.0
        
        current_confidence = self._evaluate_profile_triggers(
            current_profile, 
            self.last_recommendation is not None and 
            self._estimate_detections_from_profile(current_profile)
            or {}
        )
        
        # Only switch if new profile is significantly better
        return (new_confidence - current_confidence) > hysteresis
    
    def _estimate_detections_from_profile(self, profile: Profile) -> Dict[str, float]:
        """Estimate current detections based on profile triggers"""
        # This is a helper to reconstruct approximate detections
        detections = {}
        for trigger in profile.autoTriggers:
            category = trigger.get('category')
            threshold = trigger.get('threshold', 0.5)
            detections[category] = threshold
        return detections
    
    def get_profile_match_score(self, profile: Profile, 
                               detections: Dict[str, float]) -> float:
        """
        Get detailed match score for a profile (0-1)
        
        Args:
            profile: Profile to score
            detections: Current detections
        
        Returns:
            Score between 0 and 1
        """
        if not profile.autoTriggers:
            return 0.0
        
        scores = []
        for trigger in profile.autoTriggers:
            category = trigger.get('category')
            threshold = trigger.get('threshold', 0.5)
            detection_value = detections.get(category, 0.0)
            
            # Calculate how much above threshold we are
            if detection_value >= threshold:
                # Score is based on how far above threshold
                score = min(1.0, detection_value / (threshold * 1.5))
            else:
                # Below threshold but partial credit
                score = detection_value / threshold * 0.5
            
            scores.append(score)
        
        # Return average score
        return sum(scores) / len(scores) if scores else 0.0
    
    def get_all_profile_scores(self, detections: Dict[str, float]) -> List[Tuple[Profile, float]]:
        """
        Get match scores for all profiles
        
        Args:
            detections: Current detections
        
        Returns:
            List of (Profile, score) tuples sorted by score descending
        """
        profiles = self.profile_manager.get_all_profiles()
        scores = []
        
        for profile in profiles:
            score = self.get_profile_match_score(profile, detections)
            if score > 0:
                scores.append((profile, score))
        
        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores
