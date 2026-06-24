// ================================================================
//  alexa_bridge.js — local HTTP bridge between FRIDAY (Python)
//  and Amazon Alexa, using alexa-remote2 (Node.js, actively
//  maintained, no AWS Skill / Lambda required).
//
//  FRIDAY's iot_plugin.py talks to this server over HTTP on
//  localhost:3050. This process handles the Amazon login,
//  caches cookies to disk, and exposes simple endpoints:
//
//    GET  /health                -> { ok: true, loggedIn: bool }
//    GET  /devices                -> list of smart home devices
//    POST /command                -> run an action on a device
//
//  FIRST-TIME LOGIN
//  -----------------
//  alexa-remote2 needs a one-time interactive Amazon login (it
//  spins up a small local proxy + web page for this). Run:
//
//      node alexa_bridge.js
//
//  then open the URL it prints (default http://localhost:3052)
//  in a browser on the SAME network as this machine, and log
//  in with your Amazon account (handles 2FA/captcha normally,
//  since it's a real browser session). After a successful
//  login, alexa-remote2 saves the session to alexa-cookie.json
//  next to this file, so future restarts log in automatically
//  with no browser step.
// ================================================================

const express = require("express");
const AlexaRemote = require("alexa-remote2");
const path = require("path");
const fs = require("fs");

const COOKIE_FILE = path.join(__dirname, "alexa-cookie.json");
const PORT = process.env.ALEXA_BRIDGE_PORT || 3050;
const PROXY_PORT = process.env.ALEXA_PROXY_PORT || 3052;
const AMAZON_PAGE = process.env.AMAZON_URL || "amazon.in"; // amazon.com for US

const alexa = new AlexaRemote();
const app = express();
app.use(express.json());

let loggedIn = false;
let smarthomeDevices = []; // cached list, refreshed on demand

// ----------------------------------------------------------------
// Load previously saved cookie/registration data, if any
// ----------------------------------------------------------------
let savedCookieData = {};
if (fs.existsSync(COOKIE_FILE)) {
  try {
    savedCookieData = JSON.parse(fs.readFileSync(COOKIE_FILE, "utf8"));
    console.log("[BRIDGE] Loaded saved Alexa session.");
  } catch (e) {
    console.warn("[BRIDGE] Could not parse saved session, starting fresh.");
  }
}

// ----------------------------------------------------------------
// Initialize alexa-remote2
// ----------------------------------------------------------------
function initAlexa() {
  alexa.init(
    {
      cookie: savedCookieData.localCookie || savedCookieData.cookie || undefined,
      formerRegistrationData: savedCookieData.formerRegistrationData || savedCookieData,
      proxyOnly: true,            // we drive login via the local proxy page
      proxyOwnIp: "127.0.0.1",
      proxyPort: PROXY_PORT,
      amazonPage: AMAZON_PAGE,
      useWsMqtt: false,
      usePushConnection: false,
      cookieRefreshInterval: 0,   // 0 = let alexa-remote2 manage refresh itself
    },
    (err) => {
      if (err) {
        console.error("[BRIDGE] Init error:", err.message || err);
        if (!loggedIn) {
          console.log(
            `[BRIDGE] >>> Open http://localhost:${PROXY_PORT} in a browser ` +
              `and log in with your Amazon account to finish setup. <<<`
          );
        }
        return;
      }
      loggedIn = true;
      console.log("[BRIDGE] Alexa login successful.");
      persistSession();
      refreshDevices();
    }
  );
}

function persistSession() {
  try {
    const data = alexa.cookieData || {};
    fs.writeFileSync(COOKIE_FILE, JSON.stringify(data, null, 2));
  } catch (e) {
    console.warn("[BRIDGE] Could not persist session:", e.message);
  }
}

// Re-persist cookie whenever alexa-remote2 refreshes it
alexa.on && alexa.on("cookie", () => persistSession());

// ----------------------------------------------------------------
// Device list (smart home devices: lights, plugs, AC, fans, etc.)
// ----------------------------------------------------------------
function refreshDevices() {
  return new Promise((resolve) => {

    alexa.getSmarthomeDevices((err, devices) => {

      if (err) {
        console.error("[BRIDGE] getSmarthomeDevices error:", err);
        return resolve([]);
      }

      const found = [];

      function walk(obj) {

        if (!obj || typeof obj !== "object") {
          return;
        }

        // Found a device
        if (
          obj.friendlyName &&
          (obj.entityId || obj.applianceId)
        ) {
          found.push(normalizeDevice(obj));
        }

        // Continue searching nested objects
        for (const value of Object.values(obj)) {
          walk(value);
        }
      }

      walk(devices);

      // Remove duplicates
      const unique = [];
      const seen = new Set();

      for (const device of found) {

        if (!device.entityId) continue;

        if (seen.has(device.entityId)) continue;

        seen.add(device.entityId);

        unique.push(device);
      }

      smarthomeDevices = unique;

      console.log(
        `[BRIDGE] ${unique.length} smart home devices found`
      );

      console.log(
        unique.map(d => d.friendlyName)
      );

      resolve(unique);
    });
  });
}

// alexa-remote2 returns fairly raw Amazon "appliance" objects; pull out
// the bits FRIDAY needs and normalize capability names.
function normalizeDevice(raw) {
  const caps = [];
  (raw.capabilities || []).forEach((c) => {
    if (c.interfaceName) caps.push(c.interfaceName);
  });

  return {
    entityId: raw.entityId || raw.applianceId || raw.id,
    friendlyName: raw.friendlyName || raw.applianceName || raw.name || "",
    entityType: raw.entityType || "APPLIANCE",
    manufacturer: raw.manufacturerName || "",
    capabilities: caps,
    raw,
  };
}

// ----------------------------------------------------------------
// Execute an action on a device via Alexa's smart home directives
// ----------------------------------------------------------------
function executeAction(entityId, action, value) {

  return new Promise((resolve, reject) => {

    const parameters = buildParameters(action, value);

    if (!parameters) {
      return reject(new Error(`Unsupported action: ${action}`));
    }

    console.log("[ALEXA ACTION]");
    console.log("Entity:", entityId);
    console.log("Parameters:", JSON.stringify(parameters));

    const timeout = setTimeout(() => {
      reject(new Error("Alexa action timed out"));
    }, 15000);

    alexa.executeSmarthomeDeviceAction(
      [entityId],
      parameters,
      "APPLIANCE",
      (err, result) => {

        clearTimeout(timeout);

        if (err) {
          console.error("[ALEXA ERROR]", err);
          return reject(err);
        }

        console.log("[ALEXA RESULT]");
        console.log(JSON.stringify(result, null, 2));

        resolve(result);
      }
    );
  });
}

    
// Map FRIDAY's high-level actions onto Alexa "Action" parameters.
// These mirror the directive names Alexa's app/skill bridge accepts
// for executeSmarthomeDeviceAction.
function buildParameters(action, value) {

  switch (action) {

    case "turn_on":
      return {
        action: "turnOn"
      };

    case "turn_off":
      return {
        action: "turnOff"
      };

    case "set_brightness":
      return {
        action: "setBrightness",
        brightness: Number(value)
      };

    case "set_color":
      return {
        action: "setColor",
        colorName: String(value)
      };

    case "set_temperature":
      return {
        action: "setTargetTemperature",
        targetTemperature: Number(value)
      };

    case "set_volume":
      return {
        action: "setVolume",
        volume: Number(value)
      };

    default:
      return null;
  }
}

// ----------------------------------------------------------------
// HTTP API
// ----------------------------------------------------------------
app.get("/health", (req, res) => {
  res.json({ ok: true, loggedIn });
});

app.get("/devices", async (req, res) => {
  if (!loggedIn) {
    return res.status(503).json({ error: "Not logged in to Alexa yet." });
  }
  const force = req.query.refresh === "1";
  if (force || smarthomeDevices.length === 0) {
    await refreshDevices();
  }
  res.json({ devices: smarthomeDevices });
});

app.post("/command", async (req, res) => {
  console.log("[COMMAND REQUEST]", req.body);
  if (!loggedIn) {
    return res.status(503).json({ error: "Not logged in to Alexa yet." });
  }
  const { entityId, action, value } = req.body || {};
  if (!entityId || !action) {
    return res.status(400).json({ error: "entityId and action are required." });
  }
  try {
    console.log("[EXECUTE]", entityId, action, value);

    const result = await executeAction(entityId, action, value);

    console.log("[RESULT]", result);
    res.json({ ok: true, result });
  } catch (e) {
    res.status(500).json({ error: e.message || String(e) });
  }
});

app.listen(PORT, () => {
  console.log(`[BRIDGE] Alexa bridge listening on http://localhost:${PORT}`);
  initAlexa();
});
