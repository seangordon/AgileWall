import os
import datetime as dt
from dateutil import parser, tz

LOCAL_TZ = 'Europe/London'

def to_local_time(time_utc, dest_tz):

    dest_zone = tz.gettz(dest_tz)
    utc = parser.parse(time_utc)  # Parse Agile UTC Time String
    local_time = utc.astimezone(dest_zone)

    return local_time

def export_agile_data(rateslots, out_dir):

    # Sort slots into time order for the chart
    rateslots.sort(key=lambda x: x.valid_from)

    # Write JSON file
    # Write pw rates to file
    file_name = os.path.join(out_dir, "agile_data.js")

    print(f"Agile Chart Data = {file_name}")
   
    with open(file_name, 'w') as f:
        last = 0
        f.write(f"// Octopus Agile Daily Data\n" f"var RATES = [")
        for rate in rateslots:
            f.write(f'"{rate.price_inc}", ')
            last = rate.price_inc
        
        f.write(f'"{last}"]\n')
        f.write(f"var TIMES = [")

        for rate in rateslots:
            # Correct chart time for local time zone
            from_t = to_local_time(rate.valid_from, LOCAL_TZ)
            f.write(f'"{from_t.hour:02}:{from_t.minute:02}", ')

        f.write(f'""]\n')

    return True


def export_agile_rates(min, max, off_peak, mid_peak, peak, out_dir):

    # Write pw rates to file
    file_name = os.path.join(out_dir, "powerwall_rates.js")

    print(f"Powerwall Rate Data = {file_name}")

    with open(file_name, 'w') as f:
        f.write(f"// Powerwall Rate Ranges\n" 
                f"var MIN = {round(min,1)}\n" 
                f"var OFF_PEAK = {round(off_peak,1)}\n" 
                f"var MID_PEAK = {round(mid_peak,1)}\n" 
                f"var PEAK = {round(peak,1)}\n" 
                f"var MAX = {round(max,1)}\n"
        )

    return True