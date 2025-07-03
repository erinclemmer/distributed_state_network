import sys
from util.aes import generate_aes_key

if len(sys.argv) < 2:
    raise Exception("Usage: python create_key.py [output_key_file_location]")

location = sys.argv[1]

with open(location, 'wb') as f:
    f.write(generate_aes_key())