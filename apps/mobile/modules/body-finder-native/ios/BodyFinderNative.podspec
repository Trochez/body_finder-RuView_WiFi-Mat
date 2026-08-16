Pod::Spec.new do |s|
  s.name           = 'BodyFinderNative'
  s.version        = '0.1.0'
  s.summary        = 'Body Finder native capability adapter'
  s.description    = 'Truthful platform capability adapter for Body Finder RuView.'
  s.author         = 'Trochez'
  s.homepage       = 'https://github.com/Trochez/body_finder-RuView_WiFi-Mat'
  s.platforms      = { :ios => '15.1' }
  s.source         = { :git => '' }
  s.static_framework = true
  s.dependency 'ExpoModulesCore'
  s.source_files = '**/*.{h,m,mm,swift,hpp,cpp}'
end
