"""
Gemini LLM matcher for selecting the best YouTube video match.
"""
import logging
from typing import List, Optional, Dict, Any

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from .models import SoundtrackMetadata, YouTubeVideo, MatchScore
from .prompts import build_matching_prompt

logger = logging.getLogger(__name__)


class MatchResult(BaseModel):
	"""Structured output schema for Gemini's matching response."""
	best_match_index: int = Field(
		description="The index of the best matching video (1-indexed)"
	)
	confidence: float = Field(
		ge=0.0,
		le=1.0,
		description="Confidence score between 0.0 and 1.0"
	)
	reasoning: str = Field(
		description="Detailed explanation of why this is the best match"
	)
	key_factors: List[str] = Field(
		description="List of key factors that support this match"
	)
	concerns: List[str] = Field(
		default_factory=list,
		description="List of concerns or issues with this match"
	)


class GeminiMatcher:
	"""Uses Google's Gemini API to match soundtrack metadata with YouTube videos."""
    
	def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
		"""
		Initialize the Gemini matcher.
        
		Args:
			api_key: Google AI API key
			model_name: Name of the Gemini model to use
		"""
		self.client = genai.Client(api_key=api_key)
		self.model_name = model_name
    
	def find_best_match(
		self,
		soundtrack: SoundtrackMetadata,
		candidates: List[YouTubeVideo],
		use_comments: bool = True
	) -> tuple[Optional[YouTubeVideo], Optional[MatchScore]]:
		"""
		Find the best matching YouTube video for a soundtrack.
        
		Args:
			soundtrack: Soundtrack metadata to match
			candidates: List of candidate YouTube videos
			use_comments: Whether to include comments in the analysis
            
		Returns:
			Tuple of (best_match_video, match_score)
		"""
		if not candidates:
			logger.warning("No candidates provided for matching")
			return None, None
        
		# Build the prompt for the LLM
		prompt = build_matching_prompt(soundtrack, candidates, use_comments)
        
		try:
			# Call Gemini API with structured output
			response = self.client.models.generate_content(
				model=self.model_name,
				config=types.GenerateContentConfig(
					max_output_tokens=4096,  # Increased to avoid truncation
                    temperature=0.1,
                    top_p=0.95,
                    top_k=40,
					response_mime_type="application/json",
					response_json_schema=MatchResult.model_json_schema(),
                ),
				contents=prompt,
			)
            
			# Log raw response for debugging
			logger.debug(f"Raw Gemini response: {response.text[:500]}...")
			
			# Parse structured response using Pydantic
			match_result = MatchResult.model_validate_json(response.text)
			
			# Extract the best match (convert to 0-indexed)
			best_match_index = match_result.best_match_index - 1
			
			if best_match_index < 0 or best_match_index >= len(candidates):
				logger.warning(f"Invalid match index: {best_match_index}. Using first candidate.")
				best_match_index = 0
			
			best_match = candidates[best_match_index]
			
			# Create match score
			match_score = MatchScore(
				confidence=match_result.confidence,
				reasoning=match_result.reasoning,
				key_factors=match_result.key_factors,
				concerns=match_result.concerns
			)
			
			return best_match, match_score
            
		except Exception as e:
			logger.error(f"Error calling Gemini API: {e}")
			logger.debug(f"Response text (if available): {getattr(response, 'text', 'N/A')[:1000] if 'response' in locals() else 'N/A'}")
			# Fallback: return the first candidate with low confidence
			fallback_score = MatchScore(
				confidence=0.3,
				reasoning=f"Error in LLM matching: {str(e)[:200]}. Returning top search result as fallback.",
				key_factors=["Fallback to top search result"],
				concerns=["LLM analysis failed", f"Error type: {type(e).__name__}"]
			)
			return candidates[0], fallback_score
