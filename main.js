const { app, BrowserWindow, shell, Menu, nativeImage, dialog, ipcMain, protocol, net } = require('electron');
const { autoUpdater } = require("electron-updater");
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

let mainWindow = null;
let isQuittingForUpdate = false;
const windowsByRoomId = new Map();
const configuredWindows = new WeakSet();
const APP_PROTOCOL = 'app';
const APP_HOST = 'poker.highstakes.com';
const APP_ORIGIN = `${APP_PROTOCOL}://${APP_HOST}`;
const BUILD_DIR = path.resolve(__dirname, '..', 'build');

protocol.registerSchemesAsPrivileged([
  {
    scheme: APP_PROTOCOL,
    privileges: {
      standard: true,
      secure: true,
      supportFetchAPI: true,
      corsEnabled: true,
      stream: true,
    },
  },
]);

function getAppProtocolFilePath(requestUrl) {
  const url = new URL(requestUrl);
  if (url.hostname !== APP_HOST) return null;

  const pathname = decodeURIComponent(url.pathname || '/');
  const relativePath = pathname === '/' ? 'index.html' : pathname.replace(/^\/+/, '');
  const filePath = path.resolve(BUILD_DIR, relativePath);
  const isInsideBuild = filePath === BUILD_DIR || filePath.startsWith(`${BUILD_DIR}${path.sep}`);

  if (!isInsideBuild) return null;

  try {
    const stat = fs.statSync(filePath);
    if (stat.isFile()) return filePath;
  } catch {
    // React routes should still load the packaged app shell.
  }

  return path.join(BUILD_DIR, 'index.html');
}

function registerAppProtocol() {
  protocol.handle(APP_PROTOCOL, (request) => {
    const filePath = getAppProtocolFilePath(request.url);
    if (!filePath) {
      return new Response('Not found', { status: 404 });
    }

    return net.fetch(pathToFileURL(filePath).toString());
  });
}

function getChildWindowOptions() {
  return {
    backgroundColor: '#191A1F',
    resizable: true,
    useContentSize: true,
    minWidth: 800,
    minHeight: 600,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      nativeWindowOpen: true,
    },
  };
}

function isInternalPopupUrl(url) {
  return !url ||
    url === '' ||
    url === 'about:blank' ||
    url.startsWith(APP_ORIGIN) ||
    url.startsWith('https://gis.slotegrator.com/api/index.php/v1/client/games/launch');
}

function registerWindowRoomId(window, roomId) {
  if (!roomId || !window || window.isDestroyed()) return;
  windowsByRoomId.set(roomId, window);
}

function cleanupWindowRoomIds(window) {
  for (const [roomId, trackedWindow] of windowsByRoomId.entries()) {
    if (trackedWindow === window) {
      windowsByRoomId.delete(roomId);
    }
  }
}

function configureWindow(window) {
  if (!window || window.isDestroyed() || configuredWindows.has(window)) return;
  configuredWindows.add(window);

  window.webContents.setWindowOpenHandler(({ url }) => {
    if (isInternalPopupUrl(url)) {
      return {
        action: 'allow',
        overrideBrowserWindowOptions: getChildWindowOptions(),
      };
    }

    if (url.startsWith('http://') || url.startsWith('https://')) {
      shell.openExternal(url);
      return { action: 'deny' };
    }

    return { action: 'allow' };
  });

  window.webContents.on('did-create-window', (childWindow) => {
    configureWindow(childWindow);
  });

  window.on('closed', () => {
    cleanupWindowRoomIds(window);
  });
}

function createMainWindow() {
  const iconPath = path.join(__dirname, '..', 'public', 'pwa-512x512.png');
  const appIcon = nativeImage.createFromPath(iconPath);
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 800,
    backgroundColor: '#191A1F',
    show: false,
    title: 'HighStakes Poker',
    icon: appIcon.isEmpty() ? undefined : appIcon,
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
      nativeWindowOpen: true,
    },
  });

  mainWindow.once('ready-to-show', () => {
    if (!mainWindow) return;
    mainWindow.show();
  });

  configureWindow(mainWindow);

  mainWindow.loadURL(APP_ORIGIN).catch((err) => {
    console.error(`Failed to load ${APP_ORIGIN}`, err);
  });

  mainWindow.on("close", (e) => {
    if (isQuittingForUpdate) {
      return;
    }

    e.preventDefault();

    dialog.showMessageBox(mainWindow, {
      type: "question",
      buttons: ["Cancel", "Quit"],
      defaultId: 0,
      cancelId: 0,
      message: "Are you sure you want to quit?",
    }).then((result) => {
      if (result.response === 1) {
        mainWindow.destroy();
      }
    });
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

ipcMain.on('register-window-room-id', (event, roomId) => {
  const senderWindow = BrowserWindow.fromWebContents(event.sender);
  registerWindowRoomId(senderWindow, roomId);
});

ipcMain.on('focus-window-by-room-id', (event, roomId) => {
  const targetWindow = windowsByRoomId.get(roomId);
  if (targetWindow && !targetWindow.isDestroyed()) {
    targetWindow.focus();
  } else {
    console.warn(`No window found for roomId: ${roomId}`);
  }
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createMainWindow();
  }
});

app.whenReady().then(() => {
  registerAppProtocol();
  app.setName('HighStakes Poker');
  Menu.setApplicationMenu(null);
  createMainWindow();

  // Now that the window is created, check for updates
  setTimeout(() => {
    autoUpdater.checkForUpdatesAndNotify();
  }, 2000);
});

// Event fired when an update has been downloaded and is ready to install
autoUpdater.on('update-downloaded', (info) => {
  console.log('Update downloaded:', info);
  isQuittingForUpdate = true;

  // Notify the user
  const { dialog } = require('electron');
  dialog.showMessageBox({
    type: 'info',
    title: 'Update ready',
    message: `Version ${info.version} of the HighStakes Poker App has been downloaded. The app will now restart to apply the update.`,
    buttons: ['Restart now', 'Later'],
    defaultId: 0,
    cancelId: 1
  }).then((result) => {
    if (result.response === 0) {
      // Quit and install the update immediately
      setImmediate(() => autoUpdater.quitAndInstall());
    }
  });
});
