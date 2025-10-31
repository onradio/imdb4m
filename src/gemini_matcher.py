"""
Gemini LLM matcher for selecting the best YouTube video match.
"""
from typing import List, Optional, Dict, Any
import logging
import json
import google.generativeai as genai

from .models import SoundtrackMetadata, YouTubeVideo, MatchScore

logger = logging.getLogger(__name__)


class GeminiMatcher:
    """Uses Google's Gemini API to match soundtrack metadata with YouTube videos."""
    
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash-exp"):
        """
        Initialize the Gemini matcher.
        
        Args:
            api_key: Google AI API key
            model_name: Name of the Gemini model to use
        """
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
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
        prompt = self._build_matching_prompt(soundtrack, candidates, use_comments)
        
        try:
            # Call Gemini API
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,  # Low temperature for more deterministic results
                    "top_p": 0.95,
                    "top_k": 40,
                    "max_output_tokens": 2048,
                }
            )
            
            # Parse the response
            result = self._parse_llm_response(response.text, candidates)
            
            return result
            
        except Exception as e:
            logger.error(f"Error calling Gemini API: {e}")
            # Fallback: return the first candidate with low confidence
            fallback_score = MatchScore(
                confidence=0.3,
                reasoning=f"Error in LLM matching: {str(e)}. Returning top search result as fallback.",
                key_factors=["Fallback to top search result"],
                concerns=["LLM analysis failed"]
            )
            return candidates[0], fallback_score
    
    def _build_matching_prompt(
        self,
        soundtrack: SoundtrackMetadata,
        candidates: List[YouTubeVideo],
        use_comments: bool
    ) -> str:
        """Build the prompt for the LLM."""
        
        # Format soundtrack metadata
        soundtrack_info = f"""
## Soundtrack Metadata
- **Title**: {soundtrack.title}
- **Performer**: {soundtrack.performer or 'Unknown'}
- **Composer**: {soundtrack.composer or 'Unknown'}
- **Lyrics By**: {soundtrack.lyrics_by or 'Unknown'}
- **Producer**: {soundtrack.producer or 'Unknown'}
- **Movie**: {soundtrack.movie_title or 'Unknown'}
- **Is Traditional**: {soundtrack.is_traditional}
- **Additional Info**: {soundtrack.additional_info or 'None'}
"""
        
        # Format candidate videos
        candidates_info = []
        for i, video in enumerate(candidates, 1):
            video_info = f"""
### Candidate {i}
- **Video ID**: {video.video_id}
- **Title**: {video.title}
- **Channel**: {video.channel_title}
- **Description**: {video.description[:500] if video.description else 'No description'}...
- **Views**: {video.view_count:,}
- **Likes**: {video.like_count:,}
- **Duration**: {video.duration}
- **Published**: {video.published_at}
"""
            
            if use_comments and video.comments:
                top_comments = video.comments[:5]  # Use top 5 comments
                comments_text = "\n".join([
                    f"  - {comment.author} ({comment.like_count} likes): {comment.text[:100]}..."
                    for comment in top_comments
                ])
                video_info += f"- **Top Comments**:\n{comments_text}\n"
            
            candidates_info.append(video_info)
        
        # Construct the full prompt
        prompt = f"""You are an expert music curator tasked with finding the best YouTube video match for a specific soundtrack from a movie.

{soundtrack_info}

## Candidate YouTube Videos
{''.join(candidates_info)}

## Your Task
Analyze each candidate video and determine which one is the BEST match for the soundtrack metadata provided. Consider:

1. **Title Match**: Does the video title match the song title and performer?
2. **Artist/Performer Match**: Is the correct artist/performer featured?
3. **Context Match**: Does the description or comments mention the movie or soundtrack context?
4. **Authenticity**: Is this an official upload, high-quality recording, or authentic performance?
5. **Popularity**: Higher views/likes may indicate the canonical version (but not always)
6. **Description Quality**: Does the description provide relevant context about the song?
7. **Comments Analysis**: Do comments confirm this is the right version from the movie?

## Output Format
Respond with a JSON object in the following format:
```json
{{
  "best_match_index": <number from 1 to {len(candidates)}>,
  "confidence": <float between 0.0 and 1.0>,
  "reasoning": "<detailed explanation of why this is the best match>",
  "key_factors": ["<factor 1>", "<factor 2>", ...],
  "concerns": ["<concern 1>", "<concern 2>", ...]
}}
```

Be thorough in your analysis. If none of the candidates are good matches, set confidence below 0.5 and explain the concerns.
"""
        
        return prompt
    
    def _parse_llm_response(
        self,
        response_text: str,
        candidates: List[YouTubeVideo]
    ) -> tuple[Optional[YouTubeVideo], Optional[MatchScore]]:
        """Parse the LLM's JSON response."""
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in response")
            
            json_str = response_text[json_start:json_end]
            result = json.loads(json_str)
            
            # Extract the best match
            best_match_index = result.get('best_match_index', 1) - 1  # Convert to 0-indexed
            
            if best_match_index < 0 or best_match_index >= len(candidates):
                logger.warning(f"Invalid match index: {best_match_index}. Using first candidate.")
                best_match_index = 0
            
            best_match = candidates[best_match_index]
            
            # Create match score
            match_score = MatchScore(
                confidence=float(result.get('confidence', 0.5)),
                reasoning=result.get('reasoning', 'No reasoning provided'),
                key_factors=result.get('key_factors', []),
                concerns=result.get('concerns', [])
            )
            
            return best_match, match_score
            
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.error(f"Error parsing LLM response: {e}")
            logger.debug(f"Response text: {response_text}")
            
            # Fallback: return first candidate with low confidence
            fallback_score = MatchScore(
                confidence=0.3,
                reasoning=f"Failed to parse LLM response: {str(e)}. Returning top search result.",
                key_factors=["Fallback to top search result"],
                concerns=["Response parsing failed"]
            )
            return candidates[0], fallback_score
