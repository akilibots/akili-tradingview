import os
import pyjson5 as json

def config():
    # Load configuration

    conf = os.getenv('config')
    if conf is None:
        with open('config/config.json') as f:
            conf = f.read()
    return(json.loads(conf))
    
