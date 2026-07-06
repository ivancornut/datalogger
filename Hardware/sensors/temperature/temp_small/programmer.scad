include <BOSL2/std.scad>
difference(){
    union(){
    translate([0,0,10/2-1]){
        difference(){
            cuboid([30,8,10]);
            translate([0,0,2]){
                cuboid([31,5,10]);
            }
        }
    }
    cuboid([50,5,2]);
        translate([8,0,5.5/2+2/2]){
            cuboid([5,5,5.5]);
        }
    }
    translate([-9,0,0]){
        cyl(d = 0.9,h = 30,$fn = 100);
    }
    translate([-9+2.9,-2.4/2,0]){
        cyl(d = 0.9,h = 30,$fn = 100);
    }
    translate([-9+2.9,2.4/2,0]){
        cyl(d = 0.9,h = 30,$fn = 100);
    }
}