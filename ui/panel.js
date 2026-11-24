// SkyWatch (mod-skywatch) — Field, Ham Radio, Weather & Aviation Situational Bench UI
// Strictly XSS-safe DOM construction (zero innerHTML / outerHTML / native dialogs).
(function () {
  'use strict';

  const FLT_COLORS = {
    VFR: '#10b981',
    MVFR: '#38bdf8',
    IFR: '#ef4444',
    LIFR: '#d946ef',
  };

  function mount(host, ctx) {
    const { el } = ctx;
    const agentName = (typeof ctx.getAgentName === 'function' ? ctx.getAgentName() : ctx.agentName) || 'Agent';

    const state = {
      hud: null,
      activity: 'stargazing',
      radarOn: true,
      adsbOn: true,
      map: null,
      radarLayer: null,
      markerLayer: null,
    };

    const wrap = el('div', { className: 'sw-wrap' });
    const statusEl = el('div', { className: 'sw-status' });
    const alertsHost = el('div', { style: 'display:flex;flex-direction:column;gap:6px;' });
    const mapDiv = el('div', { className: 'sw-map', id: 'skywatchLeafletMap' });
    const kpiHost = el('div', { className: 'sw-kpi-grid' });
    const spaceHost = el('div', { className: 'sw-card' });
    const metarHost = el('div', { className: 'sw-card' });
    const windowsHost = el('div', { className: 'sw-card' });
    const briefingsHost = el('div', { className: 'sw-card' });
    const streamHost = el('div', { className: 'sw-stream', style: 'display:none;' });

    // Station Editor Controls
    const stNameIn = el('input', { className: 'sw-input', placeholder: 'Station Name', style: 'width:170px;' });
    const stLatIn = el('input', { className: 'sw-input', type: 'number', attrs: { step: '0.0001' }, placeholder: 'Lat', style: 'width:92px;' });
    const stLonIn = el('input', { className: 'sw-input', type: 'number', attrs: { step: '0.0001' }, placeholder: 'Lon', style: 'width:98px;' });
    const stIcaoIn = el('input', { className: 'sw-input', placeholder: 'ICAO (opt)', style: 'width:82px;' });
    const stAdsbIn = el('input', { className: 'sw-input', placeholder: 'Local dump1090 URL (opt)', style: 'width:190px;' });
    const actSel = el('select', { className: 'sw-select' }, [
      el('option', { value: 'stargazing', text: 'Activity: Stargazing / Astro' }),
      el('option', { value: 'drone', text: 'Activity: Drone / Part 107' }),
      el('option', { value: 'boating', text: 'Activity: Boating / Marine' }),
      el('option', { value: 'ham_field_day', text: 'Activity: Ham Radio Field Day' }),
    ]);
    actSel.addEventListener('change', () => {
      state.activity = actSel.value;
      refreshHud();
    });

    function setStatus(msg) {
      statusEl.textContent = msg || '';
      statusEl.style.display = msg ? 'block' : 'none';
    }

    function ensureMap(lat, lon) {
      if (!window.L) return null;
      if (!state.map) {
        state.map = window.L.map(mapDiv, { zoomControl: true }).setView([lat, lon], 8);
        window.L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
          attribution: '&copy; OpenStreetMap &copy; CARTO',
          maxZoom: 18,
        }).addTo(state.map);
        state.radarLayer = window.L.tileLayer(
          'https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q-900913/{z}/{x}/{y}.png',
          { opacity: 0.58, attribution: 'NEXRAD IEM' }
        );
        if (state.radarOn) state.radarLayer.addTo(state.map);
        state.markerLayer = window.L.layerGroup().addTo(state.map);
        setTimeout(() => { try { state.map.invalidateSize(); } catch (_) {} }, 180);
      } else {
        state.map.setView([lat, lon], state.map.getZoom());
      }
      return state.map;
    }

    function updateMapLayers(hud) {
      const st = hud.station;
      if (!st) return;
      const map = ensureMap(Number(st.lat), Number(st.lon));
      if (!map || !state.markerLayer) return;

      if (state.radarLayer) {
        if (state.radarOn && !map.hasLayer(state.radarLayer)) state.radarLayer.addTo(map);
        if (!state.radarOn && map.hasLayer(state.radarLayer)) map.removeLayer(state.radarLayer);
      }

      state.markerLayer.clearLayers();
      // Home station + 25nm & 50nm range rings
      const homeMarker = window.L.circleMarker([st.lat, st.lon], {
        radius: 7,
        color: '#38bdf8',
        fillColor: '#0ea5e9',
        fillOpacity: 0.9,
        weight: 2,
      });
      homeMarker.bindPopup(el('div', {}, [
        el('strong', { text: st.name }),
        el('div', { text: `${Number(st.lat).toFixed(4)}, ${Number(st.lon).toFixed(4)}` }),
      ]));
      homeMarker.addTo(state.markerLayer);

      [25, 50].forEach((nm) => {
        window.L.circle([st.lat, st.lon], {
          radius: nm * 1852,
          color: 'rgba(56,189,248,0.35)',
          weight: 1,
          dashArray: '4 4',
          fill: false,
        }).addTo(state.markerLayer);
      });

      // METAR airport pins
      const mets = (hud.aviation && hud.aviation.stations) || [];
      mets.forEach((m) => {
        if (!m.lat && !m.lon) return;
        const col = FLT_COLORS[m.flight_category] || '#94a3b8';
        const mk = window.L.circleMarker([m.lat, m.lon], {
          radius: 6,
          color: col,
          fillColor: col,
          fillOpacity: 0.75,
          weight: 2,
        });
        mk.bindPopup(el('div', { style: 'font-family:monospace;font-size:11px;' }, [
          el('strong', { text: `${m.icao} [${m.flight_category}] (${m.dist_nm} nm)` }),
          el('div', { text: m.name || '' }),
          el('div', { text: `Wind: ${m.wdir ?? '—'}° @ ${m.wspd_kt ?? '—'}kt · Vis: ${m.vis_sm ?? '—'}SM · Ceil: ${m.ceiling_ft ?? 'CLR'}ft` }),
          el('div', { style: 'margin-top:4px;opacity:0.85;', text: m.raw_ob || '' }),
        ]));
        mk.addTo(state.markerLayer);
      });

      // ADS-B aircraft markers
      if (state.adsbOn) {
        const acs = (hud.adsb && hud.adsb.aircraft) || [];
        acs.forEach((ac) => {
          const mk = window.L.circleMarker([ac.lat, ac.lon], {
            radius: 4,
            color: '#f59e0b',
            fillColor: '#fbbf24',
            fillOpacity: 0.9,
            weight: 1,
          });
          mk.bindPopup(el('div', { style: 'font-family:monospace;font-size:11px;' }, [
            el('strong', { text: `${ac.callsign || ac.icao24}` }),
            el('div', { text: `Alt: ${ac.alt_ft} ft · GS: ${ac.speed_kt} kt · HDG: ${ac.heading}°` }),
            ac.squawk ? el('div', { text: `Squawk: ${ac.squawk}` }) : null,
          ]));
          mk.addTo(state.markerLayer);
        });
      }
    }

    function renderHud(hud) {
      state.hud = hud;
      const st = hud.station || {};
      stNameIn.value = st.name || '';
      stLatIn.value = st.lat != null ? String(st.lat) : '';
      stLonIn.value = st.lon != null ? String(st.lon) : '';
      stIcaoIn.value = st.icao_hint || '';
      stAdsbIn.value = st.adsb_local_url || '';

      // 1. NWS Alerts banner
      alertsHost.replaceChildren();
      const alerts = (hud.nws && hud.nws.alerts) || [];
      alerts.forEach((al) => {
        alertsHost.appendChild(el('div', { className: 'sw-alert-banner' }, [
          el('div', { style: 'font-weight:700;', text: `⚠ [${al.severity}] ${al.event}` }),
          el('div', { style: 'font-size:11px;margin-top:2px;', text: al.headline || al.instruction || '' }),
        ]));
      });

      // 2. Top KPI Instrument Strip
      kpiHost.replaceChildren();
      const obs = (hud.nws && hud.nws.observation) || {};
      const baro = hud.baro_trend || {};
      const sw = hud.space_weather || {};
      const near = (hud.aviation && hud.aviation.nearest) || {};
      const adsb = hud.adsb || {};
      const kpis = [
        ['Surface Temp', obs.temp_f != null ? `${obs.temp_f}°F (${obs.temp_c}°C)` : '—', obs.text_description || obs.station_id || 'NWS'],
        ['Barometer', baro.latest_inhg ? `${baro.latest_inhg} inHg` : (obs.pressure_hpa ? `${obs.pressure_hpa} hPa` : '—'), baro.trend || 'STEADY'],
        ['Flight Category', near.flight_category || '—', near.icao ? `${near.icao} (${near.dist_nm}nm)` : 'No METAR'],
        ['Geomag Kp / Storm', `${sw.kp ?? '—'} (${sw.g_scale || 'G0'})`, sw.aurora_possible_here ? 'AURORA POSSIBLE' : `Aurora > ${sw.aurora_min_lat ?? '—'}°`],
        ['Solar Flux / MUF', `SFI ${sw.sfi ?? '—'}`, `Est MUF ${sw.est_muf_mhz ?? '—'} MHz · ${sw.r_scale || 'R0'}`],
        ['ADS-B Traffic', String(adsb.count ?? 0), adsb.source || 'opensky'],
      ];
      kpis.forEach(([lbl, val, sub]) => {
        kpiHost.appendChild(el('div', { className: 'sw-tile' }, [
          el('div', { className: 'sw-meta', text: lbl }),
          el('div', { className: 'sw-val', text: val }),
          el('div', { className: 'sw-meta', text: sub }),
        ]));
      });

      // 3. Space Weather & HF Ham Band Matrix
      spaceHost.replaceChildren(
        el('div', { className: 'sw-head' }, [
          el('div', { className: 'sw-title', text: 'NOAA SWPC Space Weather & HF Propagation (80m–10m)' }),
          el('span', { className: `sw-badge ${sw.kp >= 5 ? 'severe' : 'open'}`, text: `Kp ${sw.kp ?? '—'} · SFI ${sw.sfi ?? '—'} · X-Ray ${sw.xray_class || '—'}` }),
        ]),
        el('table', { className: 'sw-table' }, [
          el('thead', {}, [el('tr', {}, [
            el('th', { text: 'Band' }),
            el('th', { text: 'Freq' }),
            el('th', { text: 'Day' }),
            el('th', { text: 'Night' }),
          ])]),
          el('tbody', {}, (sw.bands || []).map((b) => el('tr', {}, [
            el('td', { style: 'font-weight:700;', text: b.band }),
            el('td', { text: `${b.freq_mhz} MHz` }),
            el('td', {}, [el('span', { className: `sw-badge ${String(b.day || '').toLowerCase()}`, text: b.day })]),
            el('td', {}, [el('span', { className: `sw-badge ${String(b.night || '').toLowerCase()}`, text: b.night })]),
          ]))),
        ])
      );

      // 4. Aviation METAR / TAF
      const mets = (hud.aviation && hud.aviation.stations) || [];
      metarHost.replaceChildren(
        el('div', { className: 'sw-head' }, [
          el('div', { className: 'sw-title', text: 'Nearby Aviation METAR & TAF' }),
          el('span', { className: 'sw-meta', text: `${mets.length} stations within ${st.radius_nm || 45} nm` }),
        ]),
        mets.length ? el('table', { className: 'sw-table' }, [
          el('thead', {}, [el('tr', {}, [
            el('th', { text: 'ICAO' }),
            el('th', { text: 'Cat' }),
            el('th', { text: 'Wind' }),
            el('th', { text: 'Vis / Ceil' }),
            el('th', { text: 'Dist' }),
          ])]),
          el('tbody', {}, mets.slice(0, 7).map((m) => el('tr', {}, [
            el('td', { style: 'font-weight:700;', text: m.icao }),
            el('td', {}, [el('span', { className: `sw-badge ${String(m.flight_category || '').toLowerCase()}`, text: m.flight_category })]),
            el('td', { text: `${m.wdir ?? '—'}°/${m.wspd_kt ?? 0}kt` }),
            el('td', { text: `${m.vis_sm ?? '—'}SM · ${m.ceiling_ft ? m.ceiling_ft + 'ft' : 'CLR'}` }),
            el('td', { text: `${m.dist_nm}nm` }),
          ]))),
        ]) : el('div', { className: 'sw-meta', text: 'No nearby METAR stations returned.' })
      );
      const tafs = (hud.aviation && hud.aviation.tafs) || [];
      if (tafs.length) {
        metarHost.appendChild(el('div', { className: 'sw-meta', style: 'white-space:pre-wrap;margin-top:4px;', text: `TAF (${tafs[0].icao}): ${tafs[0].raw_taf}` }));
      }

      // 5. 72-Hour Outdoor Activity Window Planner
      const win = hud.windows || {};
      const topW = win.top_windows || [];
      windowsHost.replaceChildren(
        el('div', { className: 'sw-head' }, [
          el('div', { className: 'sw-title', text: `72h Window Planner — ${state.activity.replace('_', ' ')}` }),
          el('span', { className: 'sw-meta', text: `Moon Illumination: ${win.moon_illumination_pct ?? '—'}%` }),
        ]),
        topW.length ? el('table', { className: 'sw-table' }, [
          el('thead', {}, [el('tr', {}, [
            el('th', { text: 'UTC Hour' }),
            el('th', { text: 'Score' }),
            el('th', { text: 'Sky / Cloud' }),
            el('th', { text: 'Wind / Gust' }),
            el('th', { text: 'Notes' }),
          ])]),
          el('tbody', {}, topW.map((w) => el('tr', {}, [
            el('td', { text: String(w.time_utc || '').replace('T', ' ').slice(0, 16) }),
            el('td', {}, [el('span', { className: `sw-badge ${String(w.rating || '').toLowerCase()}`, text: `${w.score} (${w.rating})` })]),
            el('td', { text: `${w.sky_phase} · ${w.cloud_cover_pct}%` }),
            el('td', { text: `${w.wind_kt}/${w.gust_kt} kt` }),
            el('td', { className: 'sw-meta', text: (w.reasons || []).join(', ') || 'favorable' }),
          ]))),
        ]) : el('div', { className: 'sw-meta', text: 'No window data loaded yet.' })
      );

      // 6. Saved Briefings
      const brs = hud.briefings || [];
      briefingsHost.replaceChildren(
        el('div', { className: 'sw-title', text: 'Saved Watch & Planner Briefings' }),
        brs.length ? el('div', { style: 'display:flex;flex-direction:column;gap:8px;' }, brs.map((b) => el('div', { className: 'sw-tile' }, [
          el('div', { className: 'sw-head' }, [
            el('span', { style: 'font-weight:700;color:#f8fafc;', text: b.title }),
            el('span', { className: 'sw-badge mvfr', text: b.kind }),
          ]),
          el('div', { className: 'sw-meta', style: 'white-space:pre-wrap;margin-top:4px;', text: b.summary_md }),
        ]))) : el('div', { className: 'sw-meta', text: 'No saved briefings yet. Run either ALP v1 agentic loop above.' })
      );

      updateMapLayers(hud);
    }

    async function refreshHud() {
      setStatus('Polling live NWS, AviationWeather METAR/TAF, NOAA SWPC, Open-Meteo & ADS-B...');
      const res = await ctx.action('fetch_hud', { activity: state.activity, include_adsb: state.adsbOn });
      if (res && res.status === 'ok') {
        renderHud(res);
        setStatus('');
      } else {
        setStatus((res && res.message) || 'Failed to load SkyWatch feeds');
      }
    }

    const radarBtn = el('button', {
      type: 'button',
      className: 'sw-btn active',
      text: 'NEXRAD Radar: ON',
      on: {
        click: () => {
          state.radarOn = !state.radarOn;
          radarBtn.classList.toggle('active', state.radarOn);
          radarBtn.textContent = `NEXRAD Radar: ${state.radarOn ? 'ON' : 'OFF'}`;
          if (state.hud) updateMapLayers(state.hud);
        },
      },
    });

    const adsbBtn = el('button', {
      type: 'button',
      className: 'sw-btn active',
      text: 'ADS-B Traffic: ON',
      on: {
        click: () => {
          state.adsbOn = !state.adsbOn;
          adsbBtn.classList.toggle('active', state.adsbOn);
          adsbBtn.textContent = `ADS-B Traffic: ${state.adsbOn ? 'ON' : 'OFF'}`;
          if (state.hud) updateMapLayers(state.hud);
        },
      },
    });

    const watchLoopBtn = el('button', {
      type: 'button',
      className: 'sw-btn sw-btn-amber',
      text: `Run ${agentName} Watch Briefing (ALP v1)`,
      on: {
        click: async () => {
          streamHost.style.display = 'block';
          streamHost.replaceChildren();
          setStatus('Launching Severe Weather & HF Propagation Watch (ALP v1)...');
          try {
            await ctx.launchTask('severe_weather_prop_watch', {
              station_id: state.hud && state.hud.station ? state.hud.station.id : 1,
            }, {
              streamContainer: streamHost,
              onComplete: () => { setStatus('SkyWatch briefing complete.'); refreshHud(); },
              onError: (err) => setStatus(`Loop error: ${err}`),
            });
          } catch (e) {
            setStatus(`Launch failed: ${e.message}`);
          }
        },
      },
    });

    const plannerLoopBtn = el('button', {
      type: 'button',
      className: 'sw-btn sw-btn-amber',
      text: `Run 72h ${state.activity} Planner (ALP v1)`,
      on: {
        click: async () => {
          streamHost.style.display = 'block';
          streamHost.replaceChildren();
          setStatus(`Launching 72h Outdoor Window Planner (${state.activity})...`);
          try {
            await ctx.launchTask('outdoor_window_planner', {
              station_id: state.hud && state.hud.station ? state.hud.station.id : 1,
              activity: state.activity,
            }, {
              streamContainer: streamHost,
              onComplete: () => { setStatus('Window Planner complete.'); refreshHud(); },
              onError: (err) => setStatus(`Loop error: ${err}`),
            });
          } catch (e) {
            setStatus(`Launch failed: ${e.message}`);
          }
        },
      },
    });

    const controlsCard = el('div', { className: 'sw-card' }, [
      el('div', { className: 'sw-head' }, [
        el('div', { className: 'sw-title', text: 'SkyWatch Station & Controls (Zero API Keys)' }),
        el('div', { className: 'sw-row' }, [
          actSel,
          radarBtn,
          adsbBtn,
          el('button', { type: 'button', className: 'sw-btn sw-btn-primary', text: 'Refresh Live Feeds', on: { click: refreshHud } }),
        ]),
      ]),
      el('div', { className: 'sw-row' }, [
        stNameIn,
        stLatIn,
        stLonIn,
        stIcaoIn,
        stAdsbIn,
        el('button', {
          type: 'button',
          className: 'sw-btn',
          text: 'Save Station',
          on: {
            click: async () => {
              const res = await ctx.action('save_station', {
                id: state.hud && state.hud.station ? state.hud.station.id : undefined,
                name: stNameIn.value.trim() || 'Field Station',
                lat: Number(stLatIn.value),
                lon: Number(stLonIn.value),
                icao_hint: stIcaoIn.value.trim(),
                adsb_local_url: stAdsbIn.value.trim(),
                is_default: true,
              });
              if (res && res.status === 'ok') {
                setStatus('Station updated — refreshing telemetry...');
                await refreshHud();
              } else {
                setStatus((res && res.message) || 'Station update failed');
              }
            },
          },
        }),
      ]),
      el('div', { className: 'sw-row' }, [watchLoopBtn, plannerLoopBtn]),
      streamHost,
    ]);

    wrap.append(
      statusEl,
      controlsCard,
      alertsHost,
      mapDiv,
      kpiHost,
      el('div', { className: 'sw-grid-2' }, [spaceHost, metarHost]),
      windowsHost,
      briefingsHost
    );
    host.replaceChildren(wrap);
    refreshHud();
  }

  if (window.LodgeModules && typeof window.LodgeModules.register === 'function') {
    window.LodgeModules.register('skywatch', { mount });
  }
})();
