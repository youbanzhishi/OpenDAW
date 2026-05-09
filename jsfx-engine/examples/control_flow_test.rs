//! 控制流测试 (if/while/loop/spl(ch))

use jsfx_engine::{JsfxParser, JsfxVm};

fn main() {
    println!("=== JSFX 控制流测试 ===\n");
    
    // 测试 if 语句
    println!("测试 1: if 语句");
    let source = r#"
desc:If Test
@init
x = 0;
x = 1 > 0 ? 100 : 200;
"#;
    let program = JsfxParser::parse(source).unwrap();
    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);
    vm.process_sample(0.0, 0.0);
    let x = vm.runtime.get_var("x");
    println!("  x = {} (期望 100)", x);
    assert!((x - 100.0).abs() < 0.001);
    println!("  ✓ 通过\n");
    
    // 测试 loop 循环 - 单行格式
    println!("测试 2: loop 循环 (单行)");
    let source = r#"
desc:Loop Test
@init
sum = 0;
loop(5, sum += 1;);
"#;
    let program = JsfxParser::parse(source).unwrap();
    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);
    vm.process_sample(0.0, 0.0);
    let sum = vm.runtime.get_var("sum");
    println!("  sum = {} (期望 5)", sum);
    assert!((sum - 5.0).abs() < 0.001);
    println!("  ✓ 通过\n");
    
    // 测试 spl(ch) 多通道访问
    println!("测试 3: spl(ch) 多通道访问");
    let source = r#"
desc:Spl Access Test
@sample
tmp = spl0;
spl0 = spl1;
spl1 = tmp;
"#;
    let program = JsfxParser::parse(source).unwrap();
    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);
    let (out0, out1) = vm.process_sample(0.7, 0.3);
    println!("  输入: (0.7, 0.3)");
    println!("  输出: ({:.4}, {:.4}) (期望交换: 0.3, 0.7)", out0, out1);
    assert!((out0 - 0.3).abs() < 0.001);
    assert!((out1 - 0.7).abs() < 0.001);
    println!("  ✓ 通过\n");
    
    // 测试 while 循环
    println!("测试 4: while 循环");
    let source = r#"
desc:While Test
@init
i = 0;
sum = 0;
while(i < 10,
  sum += i;
  i += 1;
);
"#;
    let program = JsfxParser::parse(source).unwrap();
    let mut vm = JsfxVm::new();
    vm.load(&program).unwrap();
    vm.init(44100.0);
    vm.process_sample(0.0, 0.0);
    let sum = vm.runtime.get_var("sum");
    println!("  sum = {} (期望 45)", sum);
    assert!((sum - 45.0).abs() < 0.001);
    println!("  ✓ 通过\n");
    
    println!("=== 全部控制流测试通过! ===");
}
