//! 内置函数测试

use jsfx_engine::{JsfxParser, JsfxVm};

fn test_builtin(name: &str, expr: &str, expected: f64, tolerance: f64) -> bool {
    let source = format!(
        r#"
desc:Test {}
slider1:0<-100,100,1>Value

@init
result = {};

@sample
result = {};
"#,
        name, expr, expr
    );

    let program = JsfxParser::parse(&source).expect(&format!("解析 {} 失败", name));
    let mut vm = JsfxVm::new();
    vm.load(&program).expect("加载失败");
    vm.init(44100.0);
    vm.process_sample(1.0, 0.0);

    let actual = vm.runtime.get_var("result");
    let diff = (actual - expected).abs();
    let passed = diff < tolerance;
    let status = if passed { "✓" } else { "✗" };
    println!(
        "  {:12}: expected={:12.6} actual={:12.6} diff={:.2e} {}",
        name, expected, actual, diff, status
    );
    passed
}

fn main() {
    println!("=== JSFX 内置函数测试 ===\n");

    let mut all_passed = true;

    // 数学函数
    println!("数学函数:");
    all_passed &= test_builtin("abs_pos", "abs(5.0)", 5.0, 0.0001);
    all_passed &= test_builtin("abs_neg", "abs(-5.0)", 5.0, 0.0001);
    all_passed &= test_builtin("sqrt_4", "sqrt(4.0)", 2.0, 0.0001);
    all_passed &= test_builtin("sqrt_9", "sqrt(9.0)", 3.0, 0.0001);
    all_passed &= test_builtin("pow_2_3", "pow(2.0, 3.0)", 8.0, 0.0001);
    all_passed &= test_builtin("pow_3_2", "pow(3.0, 2.0)", 9.0, 0.0001);
    all_passed &= test_builtin("exp_0", "exp(0.0)", 1.0, 0.0001);
    all_passed &= test_builtin("log_e", "log(1.0)", 0.0, 0.0001);

    println!("\n三角函数:");
    all_passed &= test_builtin("sin_0", "sin(0.0)", 0.0, 0.0001);
    all_passed &= test_builtin("sin_pi_2", "sin($pi/2)", 1.0, 0.0001);
    all_passed &= test_builtin("cos_0", "cos(0.0)", 1.0, 0.0001);
    all_passed &= test_builtin("cos_pi", "cos($pi)", -1.0, 0.0001);

    println!("\n比较函数:");
    all_passed &= test_builtin("min_3_5", "min(3.0, 5.0)", 3.0, 0.0001);
    all_passed &= test_builtin("max_3_5", "max(3.0, 5.0)", 5.0, 0.0001);

    println!("\n数学常量:");
    all_passed &= test_builtin("pi", "$pi", std::f64::consts::PI, 0.0001);
    all_passed &= test_builtin("e", "$e", std::f64::consts::E, 0.0001);

    println!("\n组合运算:");
    all_passed &= test_builtin("complex", "abs(sin(0.0)) + max(1.0, 2.0)", 2.0, 0.0001);

    // 三目运算
    println!("\n三目运算:");
    all_passed &= test_builtin("ternary_t", "1 > 0 ? 10.0 : 20.0", 10.0, 0.0001);
    all_passed &= test_builtin("ternary_f", "1 < 0 ? 10.0 : 20.0", 20.0, 0.0001);

    println!(
        "\n{}",
        if all_passed {
            "=== 全部测试通过! ==="
        } else {
            "=== 有测试失败 ==="
        }
    );
}
