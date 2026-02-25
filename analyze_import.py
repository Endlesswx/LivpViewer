import sys
lines = open("import_time.log").readlines()
data = []
for line in lines:
    if "import time:" in line and "|" in line:
        parts = line.split("|")
        self_time = int(parts[0].replace("import time:", "").strip())
        cum_parts = parts[1].strip().split()
        cum_time = int(cum_parts[0])
        name = parts[1][parts[1].index(cum_parts[0])+len(cum_parts[0]):].strip()
        data.append((cum_time, self_time, name))

data.sort(reverse=True)
for row in data[:20]:
    print(f"{row[0]/1000:.1f}ms (self: {row[1]/1000:.1f}ms) - {row[2]}")
