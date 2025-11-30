"""
Prompts and system roles for Gemini LLM interactions.
"""
from typing import List

from .models import SoundtrackMetadata, YouTubeVideo


def build_matching_prompt(
	soundtrack: SoundtrackMetadata,
	candidates: List[YouTubeVideo],
	use_comments: bool = True
) -> str:
	"""
	Build the prompt for matching a soundtrack to YouTube videos.
	
	Args:
		soundtrack: Soundtrack metadata to match
		candidates: List of candidate YouTube videos
		use_comments: Whether to include comments in the analysis
		
	Returns:
		Formatted prompt string for the LLM
	"""
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
			top_comments = video.comments[:5]
			comments_text = "\n".join([
				f"  - {comment.author}: {comment.text[:80]}..."
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

## Your Response
Select the best match and provide:
- **best_match_index**: The candidate number (1 to {len(candidates)})
- **confidence**: Score from 0.0 to 1.0
- **reasoning**: Detailed explanation of your choice
- **key_factors**: List of supporting factors
- **concerns**: Any issues or uncertainties (if none of the candidates are good matches, set confidence below 0.5)

Be thorough in your analysis.
"""
	
	return prompt
