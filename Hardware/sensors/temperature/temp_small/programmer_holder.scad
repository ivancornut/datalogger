include <BOSL2/std.scad>

union(){
    cuboid([47,20,4])
    translate([20,0,15/2+2]){
        difference(){
            cuboid([7,10,15]);
            translate([0,0,15/2-2/2]){
                cuboid([10,5.2,2]);
            }
        }
    }
    translate([-20,0,15/2+2]){
        difference(){
            cuboid([7,10,15]);
            translate([0,0,15/2-2/2]){
                cuboid([10,5.2,2]);
            }
        }
    }
}