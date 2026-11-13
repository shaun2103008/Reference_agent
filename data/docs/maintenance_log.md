# Maintenance log — bed 3 sensor station, September 2026

## 2026-09-01 — Season start

Station brought back into service. Probe A calibrated: dry reference 4 per cent, wet reference 91 per cent. Within tolerance. Temperature and humidity sensor replaced with a new unit after last season's failure. Light sensor cleaned.

Irrigation controller set to run 06:00 daily for 12 minutes.

## 2026-09-09 — Irrigation failure

Soil moisture had declined steadily from 42 per cent on the 1st to 19 per cent by the 9th with no sawtooth, indicating the daily irrigation had not been reaching the bed. Found the inline filter blocked with grit. Cleaned filter and ran a manual 20-minute cycle on the evening of the 9th.

Note for next season: a flat decline over more than four days should trigger an alert. We lost eight days before anyone looked at the graph.

## 2026-09-10 — Recovery confirmed

Moisture recovered to 46 per cent after the manual cycle, consistent with the wet reference, so the probe itself is sound. Automatic schedule resumed.

## 2026-09-19 — Heat event

Air temperature reached 33.1 degrees, the highest so far this season, rising to 34.2 on the 20th. Soil moisture fell faster than the usual decline, reaching 20 per cent by the 20th despite irrigation running normally. This is evapotranspiration, not a fault.

Increased irrigation to twice daily, 06:00 and 18:00, for the duration of the heat.

## 2026-09-24 — Second decline investigated

Moisture reached 11 per cent on the 24th, the lowest reading of the month. Initially suspected a second filter blockage. Inspection found the filter clear and the emitters flowing. Cause was the twice-daily schedule having been reverted to once daily on the 22nd by a controller firmware update that reset the schedule to defaults.

Schedule restored on the evening of the 24th. Firmware auto-update disabled.

## 2026-09-26 — Rain

Natural rainfall over the 25th to 27th brought moisture to 58 per cent, the highest of the month. Irrigation suspended for three days. Light readings fell to 5,200 lux on the 27th, consistent with heavy overcast.

## Outstanding actions

- Fit a pressure switch downstream of the filter so a blockage raises an alert rather than waiting for the moisture graph to be noticed.
- Probe A due for recalibration at the start of the next season.
- Replace the cable on probe B; sheath is cracked where it leaves the conduit.
