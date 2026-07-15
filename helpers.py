import os
from fhirclient import client
import requests

def path_exists(path):
    if os.path.exists(path):
        return True
    else:
        print("Error: "+path+" does not exist.")
        return False

def init(filename):
    fh = open(filename, "w+")
    return fh 

## 
#    Validate a resource
#    Create a request to onto r4 for validating the ValueSet and ConceptMap resources

def validate_resource(data,resource_type,endpoint):
    settings = {
                'app_id': 'build_rrs',
                'api_base': endpoint
            }
    validate_url = "{0}/{1}/$validate".format(settings['api_base'],resource_type)
    #smart = client.FHIRClient(settings=settings)
    response = requests.post(validate_url, json=data)
    return response.status_code

