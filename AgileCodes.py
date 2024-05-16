import requests

# Dumps all the publicly available Octopus Tariffs along with their code and description


class Product:
    def __init__(self, code, direction, full_name, description, is_variable, brand):
        self.code = code
        self.direction = direction
        self.full_name = full_name
        self.description = description
        self.is_variable = is_variable
        self.brand = brand

    def __repr__(self):
        return (f"{self.code}, {self.full_name}, {str(self.is_variable)}, {str(self.brand)}, "
                f"{str(self.direction)} \n {str(self.description)}")


headers = {"content-type": "application/json"}
url = f"https://api.octopus.energy/v1/products"

r = requests.get(url, headers=headers)
results = r.json()["results"]
if len(results) == 0:
    print(f"No Rate Codes Returned from Octopus API")
    exit(1)

rate_codes = []
for rate in results:
    rate_codes.append(Product(rate["code"], rate["direction"], rate["full_name"],
                              rate["description"], rate["is_variable"], rate["brand"]))
    
for item in rate_codes:
    print(item)
