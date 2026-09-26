generated and deliverred real syn packets (packets with no payload data )

the receiver held half oopen connection bcz of them 

checksum.py : 
    1'S complement sum of 16 bit words : folded and inverted . both ipb4 and tcp checksums call this one 

ipv4.py   :
    builds a 20 byte no options ipv4 header 

tcp.py : 
    builds a 20 byte tcp header with SYN=1

packet.py: 
    glues the ipv4 header and tcp header . no ethernet frame - thats linux's job once the packet hits the raw socket 

generator.py:
    the actual sender 


--rate N : requested packets/second ... total across all workers 
--workers N: number of parallel OS processes , each with its own raw socket