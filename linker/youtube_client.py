"""
YouTube API client for searching and fetching video metadata.
"""
from typing import List, Optional
import logging
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .models import YouTubeVideo, YouTubeComment

logger = logging.getLogger(__name__)


class YouTubeClient:
	"""Client for interacting with YouTube Data API v3."""
    
	def __init__(self, api_key: str):
		"""
		Initialize the YouTube client.
        
		Args:
			api_key: YouTube Data API v3 key
		"""
		self.api_key = api_key
		self.youtube = build('youtube', 'v3', developerKey=api_key)
    
	def search_videos(
		self, 
		query: str, 
		max_results: int = 10,
		order: str = 'relevance'
	) -> List[YouTubeVideo]:
		"""
		Search for videos on YouTube.
        
		Args:
			query: Search query
			max_results: Maximum number of results to return
			order: Sort order (relevance, viewCount, date, rating)
            
		Returns:
			List of YouTubeVideo objects
		"""
		try:
			# Search for videos
			search_response = self.youtube.search().list(
				q=query,
				part='id,snippet',
				maxResults=max_results,
				type='video',
				order=order,
				videoCategoryId='10',  # Music category
			).execute()
            
			video_ids = [item['id']['videoId'] for item in search_response.get('items', [])]
            
			if not video_ids:
				logger.warning(f"No videos found for query: {query}")
				return []
            
			# Get detailed video information
			videos = self._get_video_details(video_ids)
            
			return videos
            
		except HttpError as e:
			logger.error(f"YouTube API error: {e}")
			raise
    
	def _get_video_details(self, video_ids: List[str]) -> List[YouTubeVideo]:
		"""
		Get detailed information for a list of video IDs.
        
		Args:
			video_ids: List of YouTube video IDs
            
		Returns:
			List of YouTubeVideo objects with detailed metadata
		"""
		try:
			videos_response = self.youtube.videos().list(
				part='snippet,contentDetails,statistics',
				id=','.join(video_ids)
			).execute()
            
			videos = []
			for item in videos_response.get('items', []):
				video = YouTubeVideo(
					video_id=item['id'],
					title=item['snippet']['title'],
					url=f"https://www.youtube.com/watch?v={item['id']}",
					description=item['snippet'].get('description', ''),
					channel_title=item['snippet'].get('channelTitle', ''),
					published_at=item['snippet'].get('publishedAt', ''),
					view_count=int(item['statistics'].get('viewCount', 0)),
					like_count=int(item['statistics'].get('likeCount', 0)),
					duration=item['contentDetails'].get('duration', ''),
				)
				videos.append(video)
            
			return videos
            
		except HttpError as e:
			logger.error(f"Error fetching video details: {e}")
			raise
    
	def get_video_comments(
		self, 
		video_id: str, 
		max_results: int = 20,
		order: str = 'relevance'
	) -> List[YouTubeComment]:
		"""
		Get comments for a specific video.
        
		Args:
			video_id: YouTube video ID
			max_results: Maximum number of comments to retrieve
			order: Sort order (time, relevance)
            
		Returns:
			List of YouTubeComment objects
		"""
		try:
			comments_response = self.youtube.commentThreads().list(
				part='snippet',
				videoId=video_id,
				maxResults=max_results,
				order=order,
				textFormat='plainText'
			).execute()
            
			comments = []
			for item in comments_response.get('items', []):
				comment_snippet = item['snippet']['topLevelComment']['snippet']
				comment = YouTubeComment(
					author=comment_snippet.get('authorDisplayName', ''),
					text=comment_snippet.get('textDisplay', ''),
					like_count=int(comment_snippet.get('likeCount', 0)),
					published_at=comment_snippet.get('publishedAt', '')
				)
				comments.append(comment)
            
			return comments
            
		except HttpError as e:
			# Comments might be disabled for the video
			if e.resp.status == 403:
				logger.warning(f"Comments are disabled for video {video_id}")
				return []
			logger.error(f"Error fetching comments: {e}")
			raise
    
	def enrich_videos_with_comments(
		self, 
		videos: List[YouTubeVideo], 
		max_comments_per_video: int = 20
	) -> List[YouTubeVideo]:
		"""
		Add comments to a list of videos.
        
		Args:
			videos: List of YouTubeVideo objects
			max_comments_per_video: Maximum comments to fetch per video
            
		Returns:
			List of YouTubeVideo objects with comments added
		"""
		enriched_videos = []
        
		for video in videos:
			try:
				comments = self.get_video_comments(
					video.video_id, 
					max_results=max_comments_per_video
				)
				# Create a new video object with comments
				enriched_video = video.model_copy(update={"comments": comments})
				enriched_videos.append(enriched_video)
                
			except Exception as e:
				logger.warning(f"Failed to fetch comments for {video.video_id}: {e}")
				# Add video without comments
				enriched_videos.append(video)
        
		return enriched_videos
