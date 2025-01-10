import os

from .file import File
from helpers import secondsToHMS


class Video(File):

	def __init__(self):
		super().__init__()
		self.media = None
		self.title = None
		self.year = None
		self.language = None
		self.metadata = None
		self.prefix = None
		self.suffix = None

	@property
	def basename(self):

		def getDuration():
			duration = self.metadata.get("video_duration")
			return secondsToHMS(duration) if duration else None

		def getExtension():
			return self.extension.upper()

		def getResolution():
			width = self.metadata.get("video_width")
			height = self.metadata.get("video_height")
			return f"{width}x{height}" if width and height else None

		valueMap = {
			"duration": getDuration,
			"extension": getExtension,
			"resolution": getResolution,
		}
		prefix = "".join(f"[{value}] " for item in self.prefix if (value := valueMap[item]())) if self.prefix else ""
		suffix = "".join(f" [{value}]" for item in self.suffix if (value := valueMap[item]())) if self.suffix else ""
		return f"{prefix}{os.path.splitext(self.remoteName)[0]}{suffix}"

	def getSTRMContents(self, driveID):
		self.metadata.update({"drive_id": driveID, "file_id": self.id, "encrypted": str(self.encrypted)})
		return "plugin://plugin.video.gdrive/?mode=video" + "".join([f"&{k}={v}"for k, v in self.metadata.items() if v])

	def setData(self, video, metadata, prefix, suffix):
		self.title = video["title"]
		self.year = video["year"]
		self.language = video["language"]
		self.metadata = metadata
		self.prefix = prefix
		self.suffix = suffix


class Movie(Video):

	def formatName(self, cacheManager, titleIdentifier):
		titleInfo = cacheManager.getMovie({"original_title": self.title, "original_year": self.year})

		if titleInfo:
			title = titleInfo["new_title"]
			year = titleInfo["new_year"]
			return {"title": title, "year": year, "filename": f"{title} ({year})"}

		titleInfo = titleIdentifier.processTitle(self.title, self.year, "movie")

		if titleInfo:
			title, year = titleInfo
			cacheManager.addMovie({"original_title": self.title, "original_year": self.year, "new_title": title, "new_year": year})
			return {"title": title, "year": year, "filename": f"{title} ({year})"}


class Episode(Video):

	def __init__(self):
		super().__init__()
		self.season = None
		self.episode = None

	def setData(self, video, metadata, prefix, suffix):
		super().setData(video, metadata, prefix, suffix)
		self.season = video["season"]
		self.episode = video["episode"]

	def formatName(self, cacheManager, titleIdentifier):
		season = f"{int(self.season):02d}"

		if isinstance(self.episode, int):
			episode = f"{self.episode:02d}"
		else:
			episode = "-".join(f"{e:02d}" for e in self.episode)

		titleInfo = cacheManager.getSeries({"original_title": self.title, "original_year": self.year})

		if titleInfo:
			title = titleInfo["new_title"]
			return {"title": title, "year": titleInfo["new_year"], "filename": f"{title} S{season}E{episode}"}

		titleInfo = titleIdentifier.processTitle(self.title, self.year, "episode")

		if titleInfo:
			title, year = titleInfo
			cacheManager.addSeries({"original_title": self.title, "original_year": self.year, "new_title": title, "new_year": year})
			return {"title": title, "year": year, "filename": f"{title} S{season}E{episode}"}
