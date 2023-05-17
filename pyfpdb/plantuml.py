from py2puml import parser, writer

input_file = 'importer.py'
output_file = 'importer.uml'

with open(input_file, 'r') as f:
    source_code = f.read()
model = parser.parse_string(source_code)

with open(output_file, 'w') as f:
    writer.write(model, f)

