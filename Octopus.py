from enum import Enum, auto
import requests
from datetime import datetime, timedelta, date, timezone
from dateutil import parser
import logging

class RateType(Enum):
    UNKNOWN = auto()
    SUPER_OFF_PEAK = auto()
    OFF_PEAK = auto()
    MID_PEAK = auto()
    PEAK = auto()


class RateTimeSlot:
    def __init__(self, valid_from, valid_to, price_exc, price_inc, tariff=RateType.UNKNOWN):
        self.valid_from = valid_from
        self.valid_to = valid_to
        self.price_exc = price_exc
        self.price_inc = price_inc
        self.tariff = tariff

    def __repr__(self):
        return f"{self.valid_from}, {self.valid_to}, {str(self.price_exc)}, {str(self.price_inc)}, {str(self.tariff)}"


class TOU_Slot:
    def __init__(self, fromDayOfWeek, toDayOfWeek, fromHour, fromMinute, toHour, toMinute):
        self.fromDayOfWeek = fromDayOfWeek
        self.toDayOfWeek = toDayOfWeek
        self.fromHour = fromHour
        self.fromMinute = fromMinute
        self.toHour = toHour
        self.toMinute = toMinute

    def __repr__(self):
        return f"{self.fromDayOfWeek}, {self.toDayOfWeek}, {self.fromHour}, {self.fromMinute}, {self.toHour}, {self.toMinute}"


class Agile:

    def __init__(self, _LOGGER):
        self._LOGGER = _LOGGER
        self.LIMIT_SUPER_OFF_PEAK=0
        self.LIMIT_OFF_PEAK=0
        self.LIMIT_MID_PEAK=0

    def __to_local_time(time_utc, dest_tz):
        
        local_time = datetime.now(tz=dest_tz)

        return local_time


    def get_agile_rates(self, tariff_code, area_code, day_offset=0):
        # Note: Octopus Agile API returns tariff data in UTC
        # Check day offset is =< 0 as we can only get Agile rates for today/tomorrow or earlier days
        if day_offset > 0:
            self._LOGGER.error(f"get_agile_rates() - Attempt to fetch future tariffs, day_offset must be =< 0 : day_offset={day_offset}")
            return []

        base_url = f"https://api.octopus.energy/v1/products/{tariff_code}/electricity-tariffs"

        start_day = date.today() + timedelta(days=day_offset)
        end_day = date.today() + timedelta(days=day_offset+1)

        date_from = f"{start_day.strftime('%Y-%m-%d')}T23:00"
        date_to = f"{end_day.strftime('%Y-%m-%d')}T23:00"

        date_from = f"?period_from={date_from}"
        if date_to is not None:
            date_to = f"&period_to={date_to}"
        else:
            date_to = ""
        headers = {"content-type": "application/json"}
        url = f"{base_url}/"f"E-1R-{tariff_code}-{area_code}/" f"standard-unit-rates/{date_from}{date_to}"
        
        self._LOGGER.info(f"get_agile_rates() - url ={url}")
        
        r = requests.get(url, headers=headers)
        results = r.json()["results"]
        if len(results) == 0:
            self._LOGGER.error(f"get_agile_rates() - Tariffs not yet available for time period starting: {start_day.strftime('%Y-%m-%d')}T23:00")
            return []
        
        rate_slot_array = []
        for rate in results:
            res = RateTimeSlot(rate["valid_from"], rate["valid_to"], rate["value_exc_vat"], rate["value_inc_vat"])
            rate_slot_array.append(res)

        # Set the various thresholds based on the rate information
        if self.__set_rate_limits(rate_slot_array):
            return rate_slot_array
        else:
            self._LOGGER.error(f"get_agile_rates() - Internal Error: Bad Threshold Configuration")
            return []   # Bad threshold configuration - stop execution


    def __set_rate_limits(self, rate_slot_array):
        # Sort entire list by unit price
        rate_slot_array.sort(key=lambda x: x.price_inc)
        rate_min = rate_slot_array[0].price_inc
        rate_max = rate_slot_array[-1].price_inc

        # Caclulate the overall average rate
        rate_avg = self.get_average_rate(rate_slot_array)

        # Create the band limits
        # The split between Super Off-Peak and Off-Peak rates is the midway point between average and min rate values
        self.LIMIT_SUPER_OFF_PEAK = (((rate_avg-rate_min)/2)+rate_min) * 0.9
        # The split between Off-Peak and Mid-Peak rates is the average rate value
        self.LIMIT_OFF_PEAK = rate_avg
        # The Peak / Mid-Peak split is calulated as all rates below 50% of the max value
        self.LIMIT_MID_PEAK = (((rate_max-rate_avg)/2)+rate_avg)

        self._LOGGER.info(f"__set_rate_limits() - rate_min={rate_min}, rate_avg={rate_avg}, rate_max={rate_max}," + 
                          "LIMIT_SUPER_OFF_PEAK={self.LIMIT_SUPER_OFF_PEAK}, LIMIT_OFF_PEAK={self.LIMIT_OFF_PEAK}, LIMIT_MID_PEAK={self.LIMIT_MID_PEAK}")

        #Sanity Check the limits
        if(rate_max>self.LIMIT_MID_PEAK>self.LIMIT_OFF_PEAK>self.LIMIT_SUPER_OFF_PEAK>rate_min):
            return True
        else:
            self._LOGGER.error("__set_rate_limits() - Inconsistent Rate Thresholds found, aborting.")
            return False


    def get_super_off_peak_slots(self, agile_time_slots):
        # Tag the Super Off-Peak slots
        super_off_peak = []

        # Tag all slots below the SuperOffPeak_Limit price as "Super Off-Peak"
        for item in agile_time_slots:
            if item.price_inc < self.LIMIT_SUPER_OFF_PEAK:
                item.tariff = RateType.SUPER_OFF_PEAK
                super_off_peak.append(item)

        # Re-sort the bucket by timestamp
        super_off_peak.sort(key=lambda x: x.valid_from)

        return super_off_peak


    def get_peak_slots(self,agile_time_slots):
        peak = []
        # Tag the Peak slots as all those above the Mid-Peak Limit
        for item in agile_time_slots:
            if item.price_inc > self.LIMIT_MID_PEAK:
                item.tariff = RateType.PEAK
                peak.append(item)

        # Re-sort the bucket by timestamp
        peak.sort(key=lambda x: x.valid_from)
        return peak

    def get_off_peak_slots(self, agile_time_slots):
        off_peak = []
        # Tag the Off-Peak slots
        #  - Tag all the slots which are below the Off-Peak Limit and above the Super Off-Peak limit
        for item in agile_time_slots:
            if (item.price_inc >= self.LIMIT_SUPER_OFF_PEAK) & (item.price_inc <= self.LIMIT_OFF_PEAK):
                item.tariff = RateType.OFF_PEAK
                off_peak.append(item)

        # Re-sort the bucket by timestamp
        off_peak.sort(key=lambda x: x.valid_from)

        return off_peak


    def get_mid_peak_slots(self, agile_time_slots):
        mid_peak = []
        # Tag the Mid-Peak slots
        for item in agile_time_slots:
            if (item.price_inc >= self.LIMIT_OFF_PEAK) & (item.price_inc <= self.LIMIT_MID_PEAK):
                item.tariff = RateType.MID_PEAK
                mid_peak.append(item)

        # Re-sort the bucket by timestamp
        mid_peak.sort(key=lambda x: x.valid_from)

        return mid_peak

    # Recursive function to locate the last element in a chain of adjacent time slots
    def __find_end_slot(self, rate_time_slots, length, index=0):
        # If Start is the last element in the array, we have finished
        if index == (length - 1):
            return index

        if rate_time_slots[index].valid_to == rate_time_slots[index + 1].valid_from:
            return self.__find_end_slot(rate_time_slots, length, index + 1)
        else:  # Found the end of this series of linked slots
            return index

    # Merge any adjacent time-slots, and calculate the average unit cost for the merged slot
    def merge_adjacent_slots(self, rate_time_slots):
        merged_array = []
        slot_count = len(rate_time_slots)

        start = 0
        while start < slot_count:
            end = self.__find_end_slot(rate_time_slots, slot_count, start)

            if start != end:
                total_inc = 0
                total_exc = 0
                # Sum each rate for the included slots, so we can
                # calculate an average rate for the new merged slot
                for i in range(start, end):
                    total_inc += rate_time_slots[i].price_inc
                    total_exc += rate_time_slots[i].price_exc

                merged_array.append(RateTimeSlot(rate_time_slots[start].valid_from,
                                                rate_time_slots[end].valid_to,
                                                # Calculate Average Rate and round to 3 decimals
                                                round(total_exc / (end - start), 3),
                                                # Calculate Average Rate and round to 3 decimals
                                                round(total_inc / (end - start), 3),
                                                rate_time_slots[start].tariff)
                                    )
                start = end + 1
            else:
                merged_array.append(rate_time_slots[start])
                start = start + 1
        return merged_array


    def get_average_rate(self, rate_time_slots):
        # Caclulate the overall average rate
        total = 0
        for item in rate_time_slots:
            total += item.price_inc
        rate_avg = total/len(rate_time_slots)

        return round(rate_avg, 3)


    def __get_hour(timestr):
        time = parser.parse(timestr)
        return time.hour


    def __get_min(timestr):
        time = parser.parse(timestr)
        return time.minute

    # Build the Tesla API data structure for ToU slots
    def build_tou_periods(self, rate_time_slots):
        tou_peroids = []

        for item in rate_time_slots:
            tou_slot = {}
            tou_slot['fromDayOfWeek'] = 0
            tou_slot['toDayOfWeek'] = 6
            tou_slot['fromHour'] = Agile.__get_hour(item.valid_from)
            tou_slot['fromMinute'] = Agile.__get_min(item.valid_from)
            tou_slot['toHour'] = Agile.__get_hour(item.valid_to)
            tou_slot['toMinute'] = Agile.__get_min(item.valid_to)

            tou_peroids.append(tou_slot)
        
        return tou_peroids
    

    # Build the Tesla API data structure for Energy Costs
    def build_tou_rates(self, super_off_peak, off_peak, mid_peak, peak):
        tou_rates = []

        # Octopus supplies prices in pence, but the Powerwall expects GBP, so divide by 100
        tou_rates = {}
        tou_rates['SUPER_OFF_PEAK'] = round(super_off_peak/100, 2)
        tou_rates['OFF_PEAK'] = round(off_peak/100, 2)
        tou_rates['PARTIAL_PEAK'] = round(mid_peak/100, 2)
        tou_rates['ON_PEAK'] = round(peak/100, 2)
        
        return tou_rates
    

    def print_tou(self, name, avg_rate, rate_array):
        print(f"Average {name} Slot Rate = {avg_rate}p")
        for item in rate_array:
            print(item)


    def print_rate_slots(self, name, rate_array):
        print(f"[{name}Slots = {len(rate_array)}]")
        for item in rate_array:
            print(item)
