import teslapy
import json
from datetime import datetime, timedelta, date

class Powerwall:

    def __init__(self, tesla_id):
        self.tesla_id = tesla_id

        tesla = teslapy.Tesla(self.tesla_id)
        if not tesla.authorized:
            print('Use browser to login. "Page Not Found" will be shown on success.')
            print('Open this URL: ' + tesla.authorization_url())
            tesla.fetch_token(authorization_response=input('Enter URL after authentication: '))
        batteries = tesla.battery_list()
        print(batteries[0])
        

    def get_tariff(self):
        # Powerwall API returns schedule data in local time (DST or non-DST)

        with teslapy.Tesla(self.tesla_id) as tesla:
            batteries = tesla.battery_list()
            tariff = batteries[0].get_tariff()
        return tariff


    def set_tariff(self, battery_tariff):
        # Powerwall API returns schedule data in local time (DST or non-DST)

        with teslapy.Tesla(self.tesla_id) as tesla:
            batteries = tesla.battery_list()
            res = batteries[0].set_tariff(battery_tariff)
        return res