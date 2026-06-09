import re

# This map is used to store different types of radar data 
# and the regex patterns for matching radar types
# 这个 map 是用来放不同类型的雷达数据 匹配雷达类型的正则项的
radar_type_pat_map = {
    'LT1': r'^LT1.*\.meta\.xml$',
    'BC': r'^bc.*\.xml$',
    'CSK': r'^CSK.*\.h5$',  
    'TSX': r'(?i)^(TSX|TDX|PAZ).*\.xml$',
    'LT4': r'^JZ1.*\.(meta\.xml|tiff)$',
}

# This map is used to store different types of radar data and 
# the regex patterns for matching meta/XML files
# 这个 map 是用来放不同类型的雷达数据 匹配 meta/xml 的正则项的
is_meta_file = {
    'LT1': lambda x: bool(re.search(r'^LT1.*\.meta\.xml$', x)),
    'BC': lambda x: bool(re.search(r'^bc.*\.xml$', x)),
    'CSK': lambda x: bool(re.search(r'^CSK.*\.h5$', x)), 
    'LT4': lambda x: bool(re.search(r'^JZ1.*\.meta\.xml$', x)),
    'TSX': lambda x: bool(re.search(r'^(TSX|TDX|PAZ).*\.xml$', x, re.IGNORECASE)),
}

# This map is used to store different types of radar data and 
# the regex patterns for matching data files
# 这个 map 是用来放不同类型的雷达数据 匹配 data 的正则项的
is_data_file = { 
    'LT1': lambda x: bool(re.search(r'^LT1.*\.tiff$', x)),
    'BC': lambda x: bool(re.search(r'^bc.*\.tiff$', x)),
    'CSK': lambda x: bool(re.search(r'^CSK.*\.h5$', x)), 
    'LT4': lambda x: bool(re.search(r'^JZ1.*\.tiff$', x)),
    'TSX': lambda x: bool(re.search(r'\.(cos|cosar|dat)$', x, re.IGNORECASE)),
}


def _date_from_tsx_filename(filename):
    match = re.search(r'(20\d{6})T\d{6}', filename)
    if not match:
        match = re.search(r'(20\d{6})', filename)
    if not match:
        raise ValueError(f"Cannot extract TSX date from filename: {filename}")
    return match.group(1)

# This map is used to extract the date from the filenames of different radar types
# 这个 map 是用来从不同类型雷达数据的文件名中提取日期的
get_date_from_filename = { 
    'LT1': {'meta': lambda x: re.search(r'LT1.*_(20\d{6})', x).group(1),
            'data': lambda x: re.search(r'LT1.*_(20\d{6})', x).group(1)},
    'BC': {'meta': lambda x: re.search(r'bc.*(20\d{6})', x).group(1),
            'data': lambda x: re.search(r'bc.*(20\d{6})', x).group(1)},
    'CSK': {'meta': lambda x: re.search(r'_(20\d{6})\d{6}_', x).group(1),
            'data': lambda x: re.search(r'_(20\d{6})\d{6}_', x).group(1)}, 
    'TSX': {'meta': _date_from_tsx_filename,
            'data': _date_from_tsx_filename},
    'LT4': {'meta': lambda x: re.search(r'_(20\d{6})_', x).group(1),
            'data': lambda x: re.search(r'_(20\d{6})_', x).group(1)},
}