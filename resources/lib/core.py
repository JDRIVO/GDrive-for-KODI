import os
import sys
import glob
import json
import time
import urllib
import datetime

import xbmc
import xbmcgui
import xbmcplugin

import constants
from . import ui
from . import sync
from . import accounts
from . import filesystem
from . import google_api


class Core:

	def __init__(self):
		self.pluginHandle = int(sys.argv[1])
		self.settings = constants.settings
		self.cache = sync.cache.Cache()
		self.accountManager = accounts.manager.AccountManager(self.settings)
		self.accounts = self.accountManager.accounts
		self.cloudService = google_api.drive.GoogleDrive()
		self.dialog = xbmcgui.Dialog()

	def run(self, dbID, dbType, filePath):
		mode = self.settings.getParameter("mode", "main").lower()
		pluginQueries = self.settings.parseQuery(sys.argv[2][1:])

		modes = {
			"main": self.createMainMenu,
			"register_account": self.registerAccount,
			"add_service_account": self.addServiceAccount,
			"validate_accounts": self.validateAccounts,
			"delete_accounts": self.accountDeletion,
			"list_drive": self.createDriveMenu,
			"list_accounts": self.createAccountsMenu,
			"list_directory": self.listDirectory,
			"sync": self.sync,
			"video": self.playVideo,
			"resolution_priority": self.resolutionPriority,
			"not_implemented": self.notImplemented,
			"accounts_cm": self.accountsContextMenu,
			"list_shared_drives": self.listSharedDrives,
			"search_drive": self.searchDrive,
			"import_accounts": self.importAccounts,
			"export_accounts": self.exportAccounts,
			"set_playback_account": self.setPlaybackAccount,
			"set_alias": self.setAlias,
		}

		if mode == "video":
			modes[mode](dbID, dbType, filePath)
		else:
			modes[mode]()

		xbmcplugin.endOfDirectory(self.pluginHandle)

	def notImplemented(self):
		self.dialog.notification("gDrive", "Not implemented")

	def accountsContextMenu(self):
		options = [
			self.settings.getLocalizedString(30002),
			self.settings.getLocalizedString(30023),
			self.settings.getLocalizedString(30159),
		]
		driveID = self.settings.getParameter("drive_id")
		accountName = self.settings.getParameter("account_name")
		accountIndex = int(self.settings.getParameter("account_index"))
		selection = self.dialog.contextmenu(options)
		accounts = self.accountManager.getAccounts(driveID)
		account = accounts[accountIndex]

		if selection == 0:
			newAccountName = self.dialog.input(f"{self.settings.getLocalizedString(30002)}: {accountName}")

			if not newAccountName:
				return

			self.accountManager.renameAccount(driveID, accountIndex, newAccountName)

		elif selection == 1:
			self.cloudService.setAccount(account)
			validation = self.cloudService.refreshToken()

			if validation == "failed":
				selection = self.dialog.yesno(
					self.settings.getLocalizedString(30000),
					f"{accountName} {self.settings.getLocalizedString(30019)}",
				)

				if not selection:
					return

				self.accountManager.deleteAccount(driveID, account)

			else:
				self.dialog.ok(self.settings.getLocalizedString(30000), self.settings.getLocalizedString(30020))
				return

		elif selection == 2:
			selection = self.dialog.yesno(
				self.settings.getLocalizedString(30000),
				f"{self.settings.getLocalizedString(30121)} {accountName}?",
			)

			if not selection:
				return

			self.accountManager.deleteAccount(driveID, account)

		else:
			return

		xbmc.executebuiltin("Container.Refresh")

	def addMenu(self, url, title, cm=False, folder=True):
		listitem = xbmcgui.ListItem(title)

		if cm:
			listitem.addContextMenuItems(cm, True)

		xbmcplugin.addDirectoryItem(self.pluginHandle, url, listitem, isFolder=folder)

	def createMainMenu(self):
		pluginURL = sys.argv[0]
		syncRootPath = self.cache.getSyncRootPath()

		if syncRootPath:
			self.addMenu(
				syncRootPath,
				"[B][COLOR yellow]Browse STRM[/COLOR][/B]",
			)

		self.addMenu(
			f"{pluginURL}?mode=register_account",
			f"[COLOR yellow][B]{self.settings.getLocalizedString(30207)}[/B][/COLOR]",
			folder=False,
		)

		for driveID, accountData in self.accounts.items():
			alias = accountData["alias"]

			if alias:
				displayName = alias
			else:
				displayName = driveID

			contextMenu = [
				(
					"Force Sync",
					f"RunPlugin({pluginURL}?mode=not_implemented&drive_id={driveID})",
				),
				(
					"Rename",
					f"RunPlugin({pluginURL}?mode=set_alias&drive_id={driveID})",
				),
				(
					"Delete",
					f"RunPlugin({pluginURL}?mode=not_implemented&drive_id={driveID})",
				)
			]
			self.addMenu(
				f"{pluginURL}?mode=list_drive&drive_id={driveID}",
				displayName,
				cm=contextMenu,
			)

		xbmcplugin.setContent(self.pluginHandle, "files")
		# xbmcplugin.addSortMethod(self.pluginHandle, xbmcplugin.SORT_METHOD_FILE)
		# xbmcplugin.addSortMethod(self.pluginHandle, xbmcplugin.SORT_METHOD_LABEL_IGNORE_FOLDERS)
		xbmcplugin.addSortMethod(self.pluginHandle, xbmcplugin.SORT_METHOD_LABEL_IGNORE_FOLDERS)

	def createDriveMenu(self):
		pluginURL = sys.argv[0]
		driveID = self.settings.getParameter("drive_id")
		account = self.accountManager.getAccount(driveID)

		if not account:
			return

		self.cloudService.setAccount(account)
		self.refreshAccess(account.expiry)
		driveSettings = self.cache.getDrive(driveID)

		if driveSettings:
			self.addMenu(
				f"{pluginURL}?mode=not_implemented",
				"[COLOR yellow][B]Synced[/B][/COLOR]",
			)

		self.addMenu(
			f"{pluginURL}?mode=list_accounts&drive_id={driveID}",
			f"[B][COLOR yellow]{self.settings.getLocalizedString(30032)}[/COLOR][/B]",
		)
		self.addMenu(
			f"{pluginURL}?mode=list_directory&drive_id={driveID}",
			"My Drive",
		)
		self.addMenu(
			f"{pluginURL}?mode=list_directory&drive_id={driveID}&shared_with_me=true",
			"Shared With Me",
		)
		self.addMenu(
			f"{pluginURL}?mode=list_shared_drives&drive_id={driveID}",
			"Shared Drives",
		)
		self.addMenu(
			f"{pluginURL}?mode=search_drive&drive_id={driveID}",
			"Search",
		)
		self.addMenu(
			f"{pluginURL}?mode=list_directory&drive_id={driveID}&starred=true",
			"Starred",
		)
		xbmcplugin.setContent(self.pluginHandle, "files")
		xbmcplugin.addSortMethod(self.pluginHandle, xbmcplugin.SORT_METHOD_LABEL)

	def createAccountsMenu(self):
		pluginURL = sys.argv[0]
		driveID = self.settings.getParameter("drive_id")
		account = self.accountManager.getAccount(driveID)

		if not account:
			return

		self.cloudService.setAccount(account)
		self.refreshAccess(account.expiry)

		self.addMenu(
			f"{pluginURL}?mode=add_service_account&drive_id={driveID}",
			f"[B][COLOR yellow]{self.settings.getLocalizedString(30214)}[/COLOR][/B]",
			folder=False,
		)
		self.addMenu(
			f"{pluginURL}?mode=validate_accounts&drive_id={driveID}",
			f"[B][COLOR yellow]{self.settings.getLocalizedString(30021)}[/COLOR][/B]",
			folder=False,
		)
		self.addMenu(
			f"{pluginURL}?mode=delete_accounts&drive_id={driveID}",
			f"[COLOR yellow][B]{self.settings.getLocalizedString(30022)}[/B][/COLOR]",
			folder=False,
		)

		for index, account in enumerate(self.accountManager.getAccounts(driveID)):
			accountName = account.name
			self.addMenu(
				f"{pluginURL}?mode=accounts_cm&account_name={accountName}&account_index={index}&drive_id={driveID}",
				accountName,
				folder=False,
			)

		xbmcplugin.setContent(self.pluginHandle, "files")
		xbmcplugin.addSortMethod(self.pluginHandle, xbmcplugin.SORT_METHOD_LABEL)

	def searchDrive(self):
		pluginURL = sys.argv[0]
		driveID = self.settings.getParameter("drive_id")
		searchQuery = xbmcgui.Dialog().input("Search Query")

		if not searchQuery:
			return

		self.listDirectory(search=searchQuery)

	def listSharedDrives(self):
		pluginURL = sys.argv[0]
		driveID = self.settings.getParameter("drive_id")
		account = self.accountManager.getAccount(driveID)
		self.cloudService.setAccount(account)
		self.refreshAccess(account.expiry)
		sharedDrives = self.cloudService.getDrives()

		if sharedDrives:

			for sharedDrive in sharedDrives:
				sharedDriveID = sharedDrive["id"]
				sharedDriveName = sharedDrive["name"]
				self.addMenu(
					f"{pluginURL}?mode=list_directory&drive_id={driveID}&shared_drive_id={sharedDriveID}",
					f"[B]{sharedDriveName}[/B]",
				)

	def listDirectory(self, search=False):
		pluginURL = sys.argv[0]
		driveID = self.settings.getParameter("drive_id")
		sharedDriveID = self.settings.getParameter("shared_drive_id")
		folderID = self.settings.getParameter("folder_id")
		sharedWithMe = self.settings.getParameter("shared_with_me")
		starred = self.settings.getParameter("starred")

		if not folderID:

			if sharedDriveID:
				folderID = sharedDriveID
			else:
				folderID = driveID

		account = self.accountManager.getAccount(driveID)
		self.cloudService.setAccount(account)
		self.refreshAccess(account.expiry)
		folders = self.cloudService.listDirectory(folderID=folderID, sharedWithMe=sharedWithMe, foldersOnly=True, starred=starred, search=search)

		for folder in folders:
			folderID = folder["id"]
			folderName = folder["name"]
			folderSettings = self.cache.getFolder(folderID)

			if folderSettings:
				contextMenu = [
					(
						"Folders Sync Settings",
						f"RunPlugin({pluginURL}?mode=not_implemented&drive_id={driveID}&folder_id={folderID if folderID else driveID}&folder_name={folderName})",
					),
					(
						"Stop Folder Sync",
						f"RunPlugin({pluginURL}?mode=not_implemented&drive_id={driveID}&folder_id={folderID if folderID else driveID}&folder_name={folderName})",
					)
				]
				folderName = f"[COLOR crimson][B]{folderName}[/B][/COLOR]"
			else:
				contextMenu = [
					(
						"Sync folder",
						f"RunPlugin({pluginURL}?mode=sync&drive_id={driveID}&folder_id={folderID if folderID else driveID}&folder_name={folderName})",
					)
				]

			self.addMenu(
				f"{pluginURL}?mode=list_directory&drive_id={driveID}&folder_id={folderID}",
				folderName,
				cm=contextMenu,
			)

		xbmcplugin.setContent(self.pluginHandle, "files")
		xbmcplugin.addSortMethod(self.pluginHandle, xbmcplugin.SORT_METHOD_LABEL)

	def refreshAccess(self, expiry):
		timeNow = datetime.datetime.now()

		if timeNow >= expiry:
			self.cloudService.refreshToken()
			self.accountManager.saveAccounts()

	def sync(self):
		driveID = self.settings.getParameter("drive_id")
		folderID = self.settings.getParameter("folder_id")
		folderName = self.settings.getParameter("folder_name")
		serverPort = self.settings.getSettingInt("server_port", 8011)

		data = f"drive_id={driveID}&folder_id={folderID}&folder_name={folderName}"
		url = f"http://localhost:{serverPort}/add_sync_task"
		req = urllib.request.Request(url, data.encode("utf-8"))
		response = urllib.request.urlopen(req)
		response.close()

	def registerAccount(self):
		selection = self.dialog.ok(
			self.settings.getLocalizedString(30000),
			"{} [B][COLOR blue]http://localhost:{}/register[/COLOR][/B] {}\n\n{} [COLOR chartreuse]{}[/COLOR] {} [COLOR chartreuse]{}[/COLOR] {} [COLOR chartreuse]{}[/COLOR] [B][COLOR blue]http://localhost:{}/status[/COLOR][/B]".format(
				self.settings.getLocalizedString(30210),
				self.settings.getSetting("server_port"),
				self.settings.getLocalizedString(30218),
				self.settings.getLocalizedString(30222),
				self.settings.getLocalizedString(30223),
				self.settings.getLocalizedString(30224),
				self.settings.getLocalizedString(30225),
				self.settings.getLocalizedString(30226),
				self.settings.getLocalizedString(30227),
				self.settings.getSetting("server_port"),
			)
		)

		if selection:
			xbmc.executebuiltin("Container.Refresh")

	def addServiceAccount(self):
		accountName = self.dialog.input(self.settings.getLocalizedString(30025))

		if not accountName:
			return

		keyFilePath = self.dialog.browse(1, self.settings.getLocalizedString(30026), "files")

		if not keyFilePath:
			return

		if not keyFilePath.endswith(".json"):
			self.dialog.ok(self.settings.getLocalizedString(30000), self.settings.getLocalizedString(30027))
			return

		with open(keyFilePath, "r") as key:
			keyFile = json.loads(key.read())

		error = []

		try:
			email = keyFile["client_email"]
		except Exception:
			error.append("email")

		try:
			key = keyFile["private_key"]
		except Exception:
			error.append("key")

		if error:

			if len(error) == 2:
				self.dialog.ok(self.settings.getLocalizedString(30000), self.settings.getLocalizedString(30028))
			elif "email" in error:
				self.dialog.ok(self.settings.getLocalizedString(30000), self.settings.getLocalizedString(30029))
			elif "key" in error:
				self.dialog.ok(self.settings.getLocalizedString(30000), self.settings.getLocalizedString(30030))

			return

		account = accounts.account.Account()
		account.name = accountName
		account.email = email
		account.key = key
		self.cloudService.setAccount(account)
		outcome = self.cloudService.refreshToken()

		if outcome == "failed":
			return

		driveID = self.settings.getParameter("drive_id")
		self.accountManager.addAccount(account, driveID)
		xbmc.executebuiltin("Container.Refresh")

	def validateAccounts(self):
		driveID = self.settings.getParameter("drive_id")
		accounts = self.accountManager.getAccounts(driveID)
		accountAmount = len(accounts)
		pDialog = xbmcgui.DialogProgress()

		pDialog.create(self.settings.getLocalizedString(30306))
		deletion = False
		count = 1

		for account in list(accounts):
			accountName = account.name

			if pDialog.iscanceled():
				return

			self.cloudService.setAccount(account)
			validation = self.cloudService.refreshToken()
			pDialog.update(int(round(count / accountAmount * 100)), accountName)
			count += 1

			if validation == "failed":
				selection = self.dialog.yesno(
					self.settings.getLocalizedString(30000),
					"{accountName} {self.settings.getLocalizedString(30019)}",
				)

				if not selection:
					continue

				accounts.remove(account)
				deletion = True

		pDialog.close()
		self.dialog.ok(self.settings.getLocalizedString(30000), self.settings.getLocalizedString(30020))

		if deletion:
			xbmc.executebuiltin("Container.Refresh")

	def accountDeletion(self):
		driveID = self.settings.getParameter("drive_id")
		accounts = self.accountManager.getAccounts(driveID)
		accountNames = self.accountManager.getAccountNames(accounts)
		selection = self.dialog.multiselect(self.settings.getLocalizedString(30158), accountNames)

		if not selection:
			return

		self.accountManager.deleteAccounts(selection, accounts, driveID)
		self.dialog.ok(self.settings.getLocalizedString(30000), self.settings.getLocalizedString(30161))
		xbmc.executebuiltin("Container.Refresh")

	def resolutionPriority(self):
		resolutions = self.settings.getSetting("resolution_priority").split(", ")
		resolutionOrder = ui.resolution_order.ResolutionOrder(resolutions=resolutions)

		resolutionOrder.doModal()
		newOrder = resolutionOrder.priorityList
		del resolutionOrder

		if newOrder:
			self.settings.setSetting("resolution_priority", ", ".join(newOrder))

	def importAccounts(self):
		filePath = self.dialog.browse(1, self.settings.getLocalizedString(30033), "files", mask=".pkl")

		if not filePath:
			return

		imported = self.accountManager.mergeAccounts(filePath)

		if imported == "failed":
			self.dialog.ok(self.settings.getLocalizedString(30000), self.settings.getLocalizedString(30037))
		else:
			self.dialog.ok(self.settings.getLocalizedString(30000), self.settings.getLocalizedString(30036))

	def exportAccounts(self):
		filePath = self.dialog.browse(0, self.settings.getLocalizedString(30034), "")

		if not filePath:
			return

		self.accountManager.exportAccounts(filePath)
		self.dialog.ok(self.settings.getLocalizedString(30000), self.settings.getLocalizedString(30035))

	def setPlaybackAccount(self):
		accounts = self.accountManager.getDrives()
		displayNames = [account[1] for account in accounts]
		selection = self.dialog.select("Select an account", displayNames)

		if selection == -1:
			return

		self.settings.setSetting("playback_account", accounts[selection][0])
		self.settings.setSetting("account_override", accounts[selection][1])

	def setAlias(self):
		driveID = self.settings.getParameter("drive_id")
		alias = self.dialog.input("Drive Name:")

		if not alias:
			return

		alias = filesystem.helpers.removeProhibitedFSchars(alias)

		if alias in self.accountManager.aliases:
			self.dialog.ok("gDrive", "The drive name already exists, it must be unique.")
			return

		self.accountManager.setAlias(driveID, alias)
		driveSettings = self.cache.getDrive(driveID)
		xbmc.executebuiltin("Container.Refresh")

		if not driveSettings:
			return

		self.cache.updateDrive({"local_path": alias}, driveID)
		syncRootPath = self.cache.getSyncRootPath()
		drivePathOld = os.path.join(syncRootPath, driveSettings["local_path"])
		drivePathNew = os.path.join(syncRootPath, alias)
		filesystem.operations.FileOperations().renameFolder(syncRootPath, drivePathOld, drivePathNew)

	def playVideo(self, dbID, dbType, filePath):

		if (not dbID or not dbType) and not filePath:
			timeEnd = time.time() + 1

			while time.time() < timeEnd and (not dbID or not dbType):
				xbmc.executebuiltin("Dialog.Close(busydialog)")
				dbID = xbmc.getInfoLabel("ListItem.DBID")
				dbType = xbmc.getInfoLabel("ListItem.DBTYPE")
				filePath = xbmc.getInfoLabel("ListItem.FileNameAndPath")

		crypto = self.settings.getParameter("encrypted")
		fileID = self.settings.getParameter("file_id")
		driveURL = self.cloudService.getDownloadURL(fileID)

		if self.settings.getSetting("account_selection") == "Manually selected":
			driveID = self.settings.getSetting("playback_account")
		else:
			driveID = self.settings.getParameter("drive_id")
			account = self.accountManager.getAccount(driveID)

		account = self.accountManager.getAccount(driveID)
		self.cloudService.setAccount(account)
		self.refreshAccess(account.expiry)
		transcoded = False

		if crypto:

			if not self.settings.getSetting("crypto_password") or not self.settings.getSetting("crypto_salt"):
				self.dialog.ok(self.settings.getLocalizedString(30000), self.settings.getLocalizedString(30208))
				return

		else:
			resolutionPrompt = self.settings.getSetting("resolution_prompt")
			resolutionPriority = self.settings.getSetting("resolution_priority").split(", ")

			if resolutionPrompt:
				streams = self.cloudService.getStreams(fileID)

				if streams:
					resolutions = ["Original"] + [s[0] for s in streams]
					selection = self.dialog.select(self.settings.getLocalizedString(30031), resolutions)

					if selection == -1:
						return

					if resolutions[selection] != "Original":
						driveURL = streams[selection - 1][1]
						transcoded = resolutions[selection]

			elif resolutionPriority[0] != "Original":
				stream = self.cloudService.getStreams(fileID, resolutionPriority)

				if stream:
					transcoded, driveURL = stream

		self.accountManager.saveAccounts()
		serverPort = self.settings.getSettingInt("server_port", 8011)
		url = f"http://localhost:{serverPort}/play_url"
		data = f"encrypted={crypto}&url={driveURL}&driveid={driveID}&fileid={fileID}&transcoded={transcoded}"
		req = urllib.request.Request(url, data.encode("utf-8"))

		try:
			response = urllib.request.urlopen(req)
			response.close()
		except urllib.error.URLError as e:
			xbmc.log("gdrive error: " + str(e))
			return

		item = xbmcgui.ListItem(path=f"http://localhost:{serverPort}/play")

		if self.settings.getSetting("subtitles_format") == "Subtitles are named the same as STRM":
			subtitles = glob.glob(glob.escape(filePath.rstrip(".strm")) + "*[!gom]")
			item.setSubtitles(subtitles)
		else:
			subtitles = glob.glob(glob.escape(os.path.dirname(filePath) + os.sep) + "*[!gom]")
			item.setSubtitles(subtitles)

		if dbID:
			widget = 0 if xbmc.getInfoLabel("Container.Content") else 1
			data = f"dbid={dbID}&dbtype={dbType}&widget={widget}&track=1"
		else:
			data = "dbid=0&dbtype=0&widget=0&track=0"

		xbmcplugin.setResolvedUrl(self.pluginHandle, True, item)
		url = f"http://localhost:{serverPort}/start_player"
		req = urllib.request.Request(url, data.encode("utf-8"))
		response = urllib.request.urlopen(req)
		response.close()
