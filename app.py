import os
import logging
import pandas as pd
import streamlit as st
from dateutil import parser
import isodate
from textblob import TextBlob 
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError 
import plotly.express as px

# --- API Key Setup --
YOUTUBE_API_KEY = "AIzaSyC6W_qui40R_lj8eYu_xHjcFQbnrG-VZFA"
if not YOUTUBE_API_KEY:
    st.error("Set the YOUTUBE_API_KEY environment variable.")
    st.stop()

# --- Initialize Logging ---
logging.basicConfig(level=logging.INFO)

# --- Helper Classes and Functions ---
class YouTubeAnalytics:
    def __init__(self, api_key):
        self.youtube = build('youtube', 'v3', developerKey=api_key)

    def get_channel_stats(self, channel_ids):
        all_data = []
        try:
            request = self.youtube.channels().list(
                part='snippet,contentDetails,statistics',
                id=",".join(channel_ids)
            )
            response = request.execute()
            for item in response.get('items', []):
                data = {
                    'channelId': item['id'],
                    'channelName': item['snippet']['title'],
                    'subscriberCount': int(item['statistics'].get('subscriberCount', 0)),
                    'viewCount': int(item['statistics'].get('viewCount', 0)),
                    'videoCount': int(item['statistics'].get('videoCount', 0)),
                    'uploadsPlaylistId': item['contentDetails']['relatedPlaylists']['uploads']
                }
                all_data.append(data)
        except HttpError as e:
            st.error(f"YouTube API error: {e}")
        return pd.DataFrame(all_data)

    def get_video_ids(self, playlist_id):
        video_ids = []
        next_page_token = None
        while True:
            try:
                request = self.youtube.playlistItems().list(
                    part='contentDetails',
                    playlistId=playlist_id,
                    maxResults=50,
                    pageToken=next_page_token
                )
                response = request.execute()
                for item in response.get('items', []):
                    video_ids.append(item['contentDetails']['videoId'])
                next_page_token = response.get('nextPageToken')
                if not next_page_token:
                    break
            except HttpError:
                break
        return video_ids

    def get_video_details(self, video_ids):
        all_video_info = []
        for i in range(0, len(video_ids), 50):
            try:
                request = self.youtube.videos().list(
                    part="snippet,contentDetails,statistics",
                    id=",".join(video_ids[i:i+50])
                )
                response = request.execute()
                for video in response.get('items', []):
                    video_info = {
                        'video_id': video['id'],
                        'title': video['snippet'].get('title'),
                        'publishedAt': video['snippet'].get('publishedAt'),
                        'tags': video['snippet'].get('tags', []),
                        'viewCount': int(video['statistics'].get('viewCount', 0)),
                        'likeCount': int(video['statistics'].get('likeCount', 0)),
                        'commentCount': int(video['statistics'].get('commentCount', 0)),
                        'duration': video['contentDetails'].get('duration')
                    }
                    all_video_info.append(video_info)
            except HttpError:
                continue
        return pd.DataFrame(all_video_info)

    def preprocess(self, df):
        df['publishedAt'] = pd.to_datetime(df['publishedAt'])
        df['durationSecs'] = df['duration'].apply(lambda x: isodate.parse_duration(x).total_seconds() if pd.notnull(x) else 0)
        df['tagsCount'] = df['tags'].apply(lambda x: len(x) if isinstance(x, list) else 0)
        df['titleLength'] = df['title'].apply(lambda x: len(x))
        df['likeRatio'] = df.apply(lambda row: (row['likeCount'] / row['viewCount'] * 1000) if row['viewCount'] else 0, axis=1)
        df['commentRatio'] = df.apply(lambda row: (row['commentCount'] / row['viewCount'] * 1000) if row['viewCount'] else 0, axis=1)
        df['titleSentiment'] = df['title'].apply(lambda x: TextBlob(x).sentiment.polarity)
        return df

# --- Streamlit UI ---
st.title("📊 YouTube Channel Analytics Dashboard")

channel_input = st.text_area("Enter YouTube Channel IDs (comma-separated)", value="UCttspZesZIDEwwpVIgoZtWQ, UCRWFSbif-RFENbBrSiez1DA")
start_analysis = st.button("Start Analysis")

if start_analysis:
    with st.spinner("Fetching data..."):
        channel_ids = [c.strip() for c in channel_input.split(",")]
        yt = YouTubeAnalytics(YOUTUBE_API_KEY)
        stats_df = yt.get_channel_stats(channel_ids)

        if stats_df.empty:
            st.warning("No data fetched. Please check channel IDs.")
            st.stop()

        st.subheader("Channel Statistics")
        st.dataframe(stats_df)

        all_videos = pd.DataFrame()
        for _, row in stats_df.iterrows():
            st.info(f"Fetching videos for **{row['channelName']}**...")
            ids = yt.get_video_ids(row['uploadsPlaylistId'])
            vids_df = yt.get_video_details(ids)
            all_videos = pd.concat([all_videos, vids_df], ignore_index=True)

        if not all_videos.empty:
            all_videos = yt.preprocess(all_videos)
            st.success(f"Fetched {len(all_videos)} videos.")

            st.subheader("Video Analytics")

            st.markdown("#### Top 10 Videos by Views")
            top_videos = all_videos.sort_values("viewCount", ascending=False).head(10)
            fig1 = px.bar(top_videos, x="title", y="viewCount", title="Top Videos by Views")
            st.plotly_chart(fig1)

            st.markdown("#### Sentiment vs Views")
            fig2 = px.scatter(all_videos, x="titleSentiment", y="viewCount", size="commentCount", color="titleSentiment",
                              hover_data=["title"], title="Sentiment vs View Count")
            st.plotly_chart(fig2)

            st.markdown("#### Like & Comment Ratios")
            fig3 = px.box(all_videos, y=["likeRatio", "commentRatio"], title="Like & Comment Ratio Distribution")
            st.plotly_chart(fig3)

            st.download_button("Download Video Data as CSV", all_videos.to_csv(index=False), "video_data.csv")

            # Additional Visual Analysis (insert after line 110)
            st.subheader("📊 Additional Visual Insights")

            # 1. Video Duration Distribution
            st.markdown("### ⏱ Distribution of Video Durations")
            fig4 = px.histogram(all_videos, x='durationSecs', nbins=30, title='Distribution of Video Durations')
            st.plotly_chart(fig4)

            # 2. Views vs Likes Scatter Plot
            st.markdown("### ❤️ Views vs Likes")
            fig5 = px.scatter(all_videos, x='viewCount', y='likeCount', size='commentCount', color='title', title='Views vs Likes (Bubble Size = Comments)',hover_data=['title'])
            st.plotly_chart(fig5)

            # 3. Top 10 Most Viewed Videos
            st.markdown("### 🔝 Top 10 Most Viewed Videos")
            top_views = all_videos.nlargest(10, 'viewCount')
            fig6 = px.bar(top_views, x='title', y='viewCount', title='Top 10 Most Viewed Videos')
            st.plotly_chart(fig6)

            # 4. Engagement Rate Over Time
            st.markdown("### 📈 Engagement Over Time")
            all_videos['publishedAt'] = pd.to_datetime(all_videos['publishedAt'])
            all_videos['engagement'] = (all_videos['likeCount'] + all_videos['commentCount']) / all_videos['viewCount']
            fig7 = px.line(all_videos.sort_values('publishedAt'), x='publishedAt', y='engagement', title='Engagement Rate Over Time')
            st.plotly_chart(fig7)

            # 5. Heatmap of Engagement by Day and Hour
            st.markdown("### 🔥 Engagement Heatmap (Day vs Hour)")
            all_videos['hour'] = all_videos['publishedAt'].dt.hour
            all_videos['day'] = all_videos['publishedAt'].dt.day_name()
            heat_data = all_videos.groupby(['day', 'hour'])['engagement'].mean().reset_index()
            fig8 = px.density_heatmap(heat_data, x='hour', y='day', z='engagement', title='Engagement by Day and Hour')
            st.plotly_chart(fig8)
        else:
            st.warning("No video data found.")
