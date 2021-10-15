#!/usr/bin/env fish

for i in (seq 1 100)
    echo \{\"message\": \"message number $i\"\}
    sleep 0.5
end
